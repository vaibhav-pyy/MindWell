"""Flask CLI commands: database setup, teacher accounts, demo data, retention, schema export."""
import random
import secrets
from datetime import timedelta
from pathlib import Path

import click
from flask import current_app
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.schema import CreateIndex, CreateTable
from werkzeug.security import generate_password_hash

from .extensions import db
from .models import (Activity, ActivityCompletion, ActivitySession, CheckIn, Classroom, ClassMembership,
                     Conversation, EmergencyAlert, TeacherProfile, User, utcnow)
from .seed_data import seed_reference_data
from .services import gamification, scoring
from .utils import local_today

DEMO_DOMAIN = "demo.mindwell.local"


def register(app):
    @app.cli.command("init-db")
    @click.option("--create-database/--no-create-database", default=True,
                  help="Create the MySQL database if it does not exist (needs CREATE privilege).")
    def init_db(create_database):
        """Create the database (MySQL), all tables, and reference data. Safe to re-run."""
        url = make_url(current_app.config["SQLALCHEMY_DATABASE_URI"])
        if create_database and url.get_backend_name() == "mysql":
            # Connect without a database (URL.set(database=None) means "unchanged" in SQLAlchemy 2.1).
            server = create_engine(URL.create(url.drivername, username=url.username, password=url.password,
                                              host=url.host, port=url.port, query=url.query))
            with server.connect() as conn:
                conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{url.database}` "
                                  "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
            server.dispose()
        db.create_all()
        seed_reference_data()
        click.echo("Database ready: tables created and reference data (activities, badges) seeded.")

    @app.cli.command("create-teacher")
    @click.option("--email", required=True)
    @click.option("--name", required=True)
    @click.option("--department", default=None)
    @click.password_option(help="Prompted securely if omitted.")
    def create_teacher(email, name, department, password):
        """Create a teacher account (teachers cannot self-register)."""
        from .routes.auth import validate_password
        from .utils import ApiError
        try:
            validate_password(password)
        except ApiError as exc:
            raise click.ClickException(exc.message)
        email = email.strip().lower()
        if User.query.filter_by(email=email).first():
            raise click.ClickException("A user with that email already exists.")
        user = User(email=email, password_hash=generate_password_hash(password), role="teacher", display_name=name)
        db.session.add(user)
        db.session.flush()
        db.session.add(TeacherProfile(user_id=user.id, department=department))
        db.session.commit()
        click.echo(f"Teacher account created for {email}.")

    @app.cli.command("seed-demo")
    @click.option("--students", default=8, show_default=True)
    @click.option("--weeks", default=6, show_default=True)
    def seed_demo(students, weeks):
        """Create CLEARLY LABELLED demo data with random one-time passwords (development only)."""
        if current_app.config["APP_ENV"] == "production":
            raise click.ClickException("Refusing to seed demo data when APP_ENV=production.")
        if User.query.filter_by(is_demo=True).first():
            raise click.ClickException("Demo data already exists. Run `flask remove-demo` first.")
        from .routes.auth import create_student
        rng = random.Random()
        creds = []

        def pw():
            return secrets.token_urlsafe(9) + "7a"

        tpw = pw()
        teacher = User(email=f"teacher@{DEMO_DOMAIN}", password_hash=generate_password_hash(tpw), role="teacher",
                       display_name="Demo Teacher", is_demo=True)
        db.session.add(teacher)
        db.session.flush()
        db.session.add(TeacherProfile(user_id=teacher.id, department="Demo Department"))
        creds.append(("teacher", teacher.email, tpw))
        classroom = Classroom(name="DEMO — Section A", teacher_id=teacher.id,
                              join_code="DEMO" + secrets.token_hex(2).upper())
        db.session.add(classroom)
        db.session.flush()

        activities = Activity.query.filter(Activity.slug.isnot(None)).all()
        today = local_today()
        for i in range(students):
            spw = pw()
            s = create_student(f"student{i + 1}@{DEMO_DOMAIN}", spw, f"Demo Student {i + 1}", True, is_demo=True)
            creds.append(("student", s.email, spw))
            db.session.add(ClassMembership(class_id=classroom.id, student_id=s.id, share_aggregates=True))
            base_stress = rng.randint(2, 4)
            for d in range(weeks * 7, -1, -1):
                day = today - timedelta(days=d)
                if rng.random() < 0.45:
                    continue
                # Synthetic pattern: academic pressure drifts upward over the period (exam season).
                drift = (weeks * 7 - d) / (weeks * 7)
                c = CheckIn(student_id=s.id, checkin_date=day,
                            stress=min(5, max(1, base_stress + rng.choice([-1, 0, 0, 1]) + (1 if drift > 0.7 else 0))),
                            anxiety=rng.randint(1, 4), mood=rng.randint(2, 5),
                            sleep_hours=round(rng.uniform(5, 8.5), 1), sleep_quality=rng.randint(2, 5),
                            academic_pressure=min(5, max(1, round(2 + 2.5 * drift + rng.choice([-1, 0, 1])))),
                            stressors=rng.sample(["exams", "assignments", "sleep", "family", "future"],
                                                 k=rng.randint(0, 2)))
                scoring.apply_to_checkin(c)
                db.session.add(c)
                db.session.flush()
                gamification.award_xp(s.id, current_app.config["XP_CHECKIN"], "Daily check-in", "checkin", c.id)
                gamification.record_active_day(s.id, day)
                if rng.random() < 0.5 and activities:
                    a = rng.choice(activities)
                    started = utcnow() - timedelta(days=d, minutes=a.duration_minutes + 1)
                    sess = ActivitySession(student_id=s.id, activity_id=a.id, started_at=started,
                                           completed_at=started + timedelta(minutes=a.duration_minutes))
                    db.session.add(sess)
                    db.session.flush()
                    comp = ActivityCompletion(session_id=sess.id, student_id=s.id, activity_id=a.id,
                                              completion_date=day, elapsed_seconds=a.duration_minutes * 60,
                                              xp_awarded=a.xp_reward)
                    db.session.add(comp)
                    db.session.flush()
                    gamification.award_xp(s.id, a.xp_reward, f"Completed: {a.title}", "activity", comp.id)
            gamification.evaluate_badges(s.id)
        db.session.commit()
        click.echo("\nDEMO DATA CREATED (synthetic, labelled 'DEMO'). One-time credentials — store them safely:\n")
        for role, email, password in creds:
            click.echo(f"  {role:8} {email:40} {password}")
        click.echo(f"\nDemo class join code: {classroom.join_code}\nRemove with: flask remove-demo\n")

    @app.cli.command("remove-demo")
    def remove_demo():
        """Delete every demo account and all of its data (cascades)."""
        users = User.query.filter_by(is_demo=True).all()
        for u in users:
            db.session.delete(u)
        db.session.commit()
        click.echo(f"Removed {len(users)} demo accounts and their data.")

    @app.cli.command("purge-expired")
    def purge_expired():
        """Apply retention: delete conversations and alert logs older than the configured periods."""
        cfg = current_app.config
        conv_cutoff = utcnow() - timedelta(days=cfg["CHAT_RETENTION_DAYS"])
        alert_cutoff = utcnow() - timedelta(days=cfg["ALERT_LOG_RETENTION_DAYS"])
        convs = Conversation.query.filter(Conversation.updated_at < conv_cutoff).all()
        for c in convs:
            db.session.delete(c)
        alerts = EmergencyAlert.query.filter(EmergencyAlert.created_at < alert_cutoff).all()
        for a in alerts:
            db.session.delete(a)
        db.session.commit()
        click.echo(f"Deleted {len(convs)} conversations and {len(alerts)} alert logs past retention.")

    @app.cli.command("export-schema")
    @click.option("--out", default=str(Path(__file__).resolve().parents[2] / "database" / "schema.sql"))
    def export_schema(out):
        """Write MySQL DDL for the current models to database/schema.sql."""
        from sqlalchemy.dialects import mysql
        dialect = mysql.dialect()
        parts = ["-- MindWell schema (generated by `flask export-schema` from backend/app/models.py).",
                 "-- Preferred setup is `flask init-db`; this file is for review or manual setup.",
                 "CREATE DATABASE IF NOT EXISTS mindwell CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;",
                 "USE mindwell;", ""]
        for table in db.metadata.sorted_tables:
            ddl = str(CreateTable(table).compile(dialect=dialect)).strip()
            parts.append(ddl + " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;\n")
            for index in sorted(table.indexes, key=lambda i: i.name):
                parts.append(str(CreateIndex(index).compile(dialect=dialect)).strip() + ";")
            parts.append("")
        Path(out).write_text("\n".join(parts), encoding="utf-8")
        click.echo(f"Schema written to {out}")
