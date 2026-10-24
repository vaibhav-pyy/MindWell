import logging

from flask import Blueprint, current_app, g

from ..extensions import db, limiter, user_or_ip
from ..models import Activity, Conversation, EmergencyContact, MemoryItem, Message, utcnow
from ..security import student_required
from ..services import ai_validation, memory, prompts, recommendations, safety
from ..services.gemini import AIUnavailable, get_ai, to_contents
from ..utils import ApiError, iso, json_body, ok, req_str

bp = Blueprint("chat", __name__, url_prefix="/api")
log = logging.getLogger(__name__)


def message_dict(m, activities_by_id=None):
    acts = []
    for aid in (m.suggested_activity_ids or []):
        a = (activities_by_id or {}).get(aid) or db.session.get(Activity, aid)
        if a and a.is_active:
            acts.append({"id": a.id, "title": a.title, "duration_minutes": a.duration_minutes,
                         "category": a.category, "xp_reward": a.xp_reward})
    return {"id": m.id, "role": m.role, "source": m.source, "content": m.content,
            "safety_level": m.safety_level, "suggested_activities": acts, "created_at": iso(m.created_at)}


def conversation_dict(c, with_messages=False):
    data = {"id": c.id, "title": c.title, "created_at": iso(c.created_at), "updated_at": iso(c.updated_at)}
    if with_messages:
        data["messages"] = [message_dict(m) for m in c.messages]
    return data


def own_conversation(conv_id):
    conv = Conversation.query.filter_by(id=conv_id, student_id=g.user.id).first()
    if conv is None:
        raise ApiError("Conversation not found.", 404, "not_found")
    return conv


@bp.get("/conversations")
@student_required
def list_conversations():
    convs = (Conversation.query.filter_by(student_id=g.user.id)
             .order_by(Conversation.updated_at.desc()).limit(100).all())
    return ok([conversation_dict(c) for c in convs])


@bp.post("/conversations")
@student_required
@limiter.limit("30 per hour", key_func=user_or_ip)
def create_conversation():
    conv = Conversation(student_id=g.user.id)
    db.session.add(conv)
    db.session.flush()
    # Best effort: condense the previous conversation into memory (skipped if memory is off or AI unavailable).
    if g.user.student_profile.ai_processing_consent:
        memory.summarize_previous(g.user.id, exclude_id=conv.id)
    db.session.commit()
    return ok(conversation_dict(conv, with_messages=True), 201)


@bp.get("/conversations/<int:conv_id>")
@student_required
def get_conversation(conv_id):
    return ok(conversation_dict(own_conversation(conv_id), with_messages=True))


@bp.delete("/conversations/<int:conv_id>")
@student_required
def delete_conversation(conv_id):
    conv = own_conversation(conv_id)
    db.session.delete(conv)
    db.session.commit()
    return ok({"deleted": True})


@bp.delete("/conversations")
@student_required
def delete_all_conversations():
    convs = Conversation.query.filter_by(student_id=g.user.id).all()
    for c in convs:
        db.session.delete(c)
    db.session.commit()
    return ok({"deleted": len(convs)})


def _support_payload(level):
    contact = EmergencyContact.query.filter_by(student_id=g.user.id).first()
    return {"level": level, "show_support": level in ("concern", "crisis"),
            "has_emergency_contact": contact is not None}


@bp.post("/conversations/<int:conv_id>/messages")
@student_required
@limiter.limit("20 per minute; 300 per day", key_func=user_or_ip)
def send_message(conv_id):
    conv = own_conversation(conv_id)
    text = req_str(json_body(), "content", max_len=current_app.config["MAX_MESSAGE_CHARS"], label="Message")
    rule_level = safety.screen(text)
    support_cfg = current_app.config["SUPPORT"]

    # 1) Crisis language: fixed safety response, no AI call, support panel shown. Nobody is contacted.
    if rule_level == "crisis":
        user_msg = Message(conversation_id=conv.id, role="user", source="student", content=text,
                           safety_level="crisis")
        has_contact = EmergencyContact.query.filter_by(student_id=g.user.id).first() is not None
        reply = Message(conversation_id=conv.id, role="assistant", source="safety_template",
                        content=safety.crisis_message(support_cfg["helpline"], support_cfg["emergency_services"],
                                                      has_contact),
                        safety_level="crisis")
        db.session.add_all([user_msg, reply])
        conv.updated_at = utcnow()
        if conv.title == "New conversation":
            conv.title = "Support conversation"
        db.session.commit()
        return ok({"user_message": message_dict(user_msg), "assistant_message": message_dict(reply),
                   "safety": _support_payload("crisis"), "conversation": conversation_dict(conv)})

    # 2) AI processing requires consent.
    if not g.user.student_profile.ai_processing_consent:
        raise ApiError("To chat with the AI companion, please allow AI processing in Privacy settings. "
                       "Support options and helplines are available without it.", 403, "ai_consent_required",
                       {"safety": _support_payload(rule_level)})

    catalog = {a.slug: a for a in Activity.query.filter(Activity.slug.isnot(None), Activity.is_active).all()}
    catalog_text = "\n".join(f"- {slug}: {a.title} ({a.duration_minutes} min, {a.category})"
                             for slug, a in catalog.items())
    preamble = memory.build_context_preamble(g.user.id)
    system = prompts.CHAT_SYSTEM + "\n\nActivity catalog (slug: title):\n" + catalog_text
    if preamble:
        system += "\n\nContext for continuity:\n" + preamble
    if rule_level == "concern":
        system += ("\n\nSafety note from MindWell's rule-based screen: the latest message may indicate serious "
                   "distress. Gently check whether the student is safe and mention that human support is available.")

    history = memory.recent_history(conv, current_app.config["CHAT_CONTEXT_MESSAGES"] - 1)
    history.append(("user", text))
    try:
        raw = get_ai().generate_json(system_instruction=system, contents=to_contents(history),
                                     schema=prompts.CHAT_SCHEMA, temperature=0.7, max_output_tokens=1024)
        result = ai_validation.validate_chat(raw, set(catalog))
    except AIUnavailable as exc:
        # Nothing is stored and no substitute reply is invented; the UI keeps the text for retry.
        raise ApiError(exc.message, 503, "ai_unavailable",
                       {"reason": exc.reason, "safety": _support_payload(rule_level)})

    level = safety.combine(rule_level, result["risk_level"])
    user_msg = Message(conversation_id=conv.id, role="user", source="student", content=text, safety_level=level)
    activity_ids = [catalog[s].id for s in result["slugs"]] if level != "crisis" else []
    reply = Message(conversation_id=conv.id, role="assistant", source="gemini", content=result["reply"],
                    safety_level=level, suggested_activity_ids=activity_ids or None)
    db.session.add_all([user_msg, reply])
    for aid in activity_ids:
        recommendations.add_recommendation(g.user.id, aid, "chat", "Suggested in your conversation with MindWell.")
    if conv.title == "New conversation" and result["title"]:
        conv.title = result["title"]
    conv.updated_at = utcnow()
    db.session.commit()
    return ok({"user_message": message_dict(user_msg), "assistant_message": message_dict(reply),
               "safety": _support_payload(level), "conversation": conversation_dict(conv)})


@bp.post("/conversations/<int:conv_id>/summarize")
@student_required
@limiter.limit("20 per hour", key_func=user_or_ip)
def summarize(conv_id):
    conv = own_conversation(conv_id)
    if not g.user.student_profile.ai_processing_consent:
        raise ApiError("AI processing is turned off in your privacy settings.", 403, "ai_consent_required")
    if not g.user.student_profile.memory_enabled:
        raise ApiError("Memory is turned off in your privacy settings.", 403, "memory_disabled")
    item = memory.summarize_conversation(conv)
    db.session.commit()
    return ok({"memory_item": memory_dict(item) if item else None})


# --- Memory management -------------------------------------------------------------

def memory_dict(m):
    return {"id": m.id, "kind": m.kind,
            "label": "You wrote this" if m.kind == "student_note" else "AI-generated summary (may be imperfect)",
            "content": m.content, "source_conversation_id": m.source_conversation_id, "created_at": iso(m.created_at)}


@bp.get("/memory")
@student_required
def list_memory():
    items = MemoryItem.query.filter_by(student_id=g.user.id).order_by(MemoryItem.created_at.desc()).all()
    p = g.user.student_profile
    return ok({"memory_enabled": p.memory_enabled, "items": [memory_dict(m) for m in items]})


@bp.post("/memory")
@student_required
def add_memory():
    content = req_str(json_body(), "content", min_len=3, max_len=500, label="Note")
    if MemoryItem.query.filter_by(student_id=g.user.id, kind="student_note").count() >= 50:
        raise ApiError("You can keep up to 50 notes. Please delete some first.", 422, "limit_reached")
    item = MemoryItem(student_id=g.user.id, kind="student_note", content=content)
    db.session.add(item)
    db.session.commit()
    return ok(memory_dict(item), 201)


@bp.delete("/memory/<int:item_id>")
@student_required
def delete_memory(item_id):
    item = MemoryItem.query.filter_by(id=item_id, student_id=g.user.id).first()
    if item is None:
        raise ApiError("Memory item not found.", 404, "not_found")
    db.session.delete(item)
    db.session.commit()
    return ok({"deleted": True})


@bp.delete("/memory")
@student_required
def clear_memory():
    n = MemoryItem.query.filter_by(student_id=g.user.id).delete()
    db.session.commit()
    return ok({"deleted": n})
