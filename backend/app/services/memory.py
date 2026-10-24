"""Conversation memory: what context is sent to Gemini, scoped to one student.

Context sent with each chat turn (all queries filter on the authenticated student_id):
  1. Up to CHAT_CONTEXT_MESSAGES most recent messages of the CURRENT conversation.
  2. If memory is enabled: the student's own notes (verbatim) and the most recent
     MEMORY_SUMMARIES_IN_CONTEXT AI summaries of earlier conversations, clearly labelled.
  3. If the student opted in: their latest check-in indicator levels (numbers only).
Never sent: name, email, emergency contact, other students' data, journal entries.
"""
import logging

from flask import current_app

from ..extensions import db
from ..models import CheckIn, Conversation, MemoryItem, Message, StudentProfile
from . import ai_validation, prompts
from .gemini import AIUnavailable, get_ai, to_contents

log = logging.getLogger(__name__)


def build_context_preamble(student_id):
    profile = db.session.get(StudentProfile, student_id)
    parts = []
    if profile and profile.memory_enabled:
        notes = (MemoryItem.query.filter_by(student_id=student_id, kind="student_note")
                 .order_by(MemoryItem.created_at.desc()).limit(10).all())
        summaries = (MemoryItem.query.filter_by(student_id=student_id, kind="ai_summary")
                     .order_by(MemoryItem.created_at.desc())
                     .limit(current_app.config["MEMORY_SUMMARIES_IN_CONTEXT"]).all())
        if notes:
            parts.append("Things the student wrote for you to remember (stated by the student):\n" +
                         "\n".join(f"- {n.content}" for n in notes))
        if summaries:
            parts.append("AI-generated summaries of earlier conversations (interpretations, may be incomplete):\n" +
                         "\n".join(f"- {s.content}" for s in reversed(summaries)))
    if profile and profile.personalize_with_checkins:
        latest = (CheckIn.query.filter_by(student_id=student_id)
                  .order_by(CheckIn.checkin_date.desc()).first())
        if latest:
            fields = [("stress", latest.stress_level), ("worry", latest.anxiety_level), ("mood", latest.mood_level),
                      ("sleep", latest.sleep_score), ("academic pressure", latest.academic_pressure_level)]
            vals = ", ".join(f"{k} {round(v)}/100" for k, v in fields if v is not None)
            if vals:
                parts.append(f"Student's latest self-reported check-in ({latest.checkin_date.isoformat()}): {vals}.")
    return "\n\n".join(parts)


def recent_history(conversation, limit):
    msgs = (Message.query.filter_by(conversation_id=conversation.id)
            .order_by(Message.id.desc()).limit(limit).all())
    return [(m.role, m.content) for m in reversed(msgs)]


def summarize_conversation(conversation):
    """Create an AI summary memory item for the unsummarised part of a conversation (best effort)."""
    profile = db.session.get(StudentProfile, conversation.student_id)
    if not profile or not profile.memory_enabled:
        return None
    q = Message.query.filter_by(conversation_id=conversation.id)
    if conversation.summarized_through_message_id:
        q = q.filter(Message.id > conversation.summarized_through_message_id)
    msgs = q.order_by(Message.id).limit(40).all()
    student_msgs = [m for m in msgs if m.role == "user"]
    if len(student_msgs) < 2 or any(m.safety_level == "crisis" for m in msgs):
        # Crisis conversations are not condensed into long-term memory automatically.
        return None
    transcript = "\n".join(f"{'Student' if m.role == 'user' else 'MindWell'}: {m.content}" for m in msgs)
    try:
        data = get_ai().generate_json(system_instruction=prompts.SUMMARY_SYSTEM,
                                      contents=to_contents([("user", transcript)]),
                                      schema=prompts.SUMMARY_SCHEMA, temperature=0.2, max_output_tokens=300)
        summary = ai_validation.validate_summary(data)
    except AIUnavailable as exc:
        log.info("Summary skipped: %s", exc.reason)
        return None
    conversation.summarized_through_message_id = msgs[-1].id
    if not summary:
        return None
    item = MemoryItem(student_id=conversation.student_id, kind="ai_summary", content=summary,
                      source_conversation_id=conversation.id)
    db.session.add(item)
    return item


def summarize_previous(student_id, exclude_id=None):
    q = Conversation.query.filter_by(student_id=student_id)
    if exclude_id:
        q = q.filter(Conversation.id != exclude_id)
    previous = q.order_by(Conversation.updated_at.desc()).first()
    if previous is None:
        return None
    last = Message.query.filter_by(conversation_id=previous.id).order_by(Message.id.desc()).first()
    if last is None or (previous.summarized_through_message_id or 0) >= last.id:
        return None
    return summarize_conversation(previous)
