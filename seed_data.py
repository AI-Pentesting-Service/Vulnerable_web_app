import sys
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import User, Project, Task, Comment
from app.auth import get_password_hash
from app.config import settings

def seed_database():
    print("Starting database seeding...")

    engine = create_engine(settings.DATABASE_URL)
    Base.metadata.create_all(bind=engine)

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    try:
        existing_users = db.query(User).count()
        if existing_users > 0:
            print("Database already seeded. Skipping...")
            return

        print("Creating users...")
        users_data = [
            {
                "email": "admin@collabspace.io",
                "username": "admin",
                "full_name": "System Administrator",
                "password": "Admin123!",
                "role": "admin"
            },
            {
                "email": "alice@collabspace.io",
                "username": "alice",
                "full_name": "Alice Johnson",
                "password": "Alice123!",
                "role": "manager"
            },
            {
                "email": "bob@collabspace.io",
                "username": "bob",
                "full_name": "Bob Smith",
                "password": "Bob123!",
                "role": "member"
            },
            {
                "email": "charlie@collabspace.io",
                "username": "charlie",
                "full_name": "Charlie Brown",
                "password": "Charlie123!",
                "role": "member"
            },
            {
                "email": "diana@collabspace.io",
                "username": "diana",
                "full_name": "Diana Prince",
                "password": "Diana123!",
                "role": "member"
            }
        ]

        users = []
        for user_data in users_data:
            user = User(
                email=user_data["email"],
                username=user_data["username"],
                full_name=user_data["full_name"],
                hashed_password=get_password_hash(user_data["password"]),
                role=user_data["role"],
                is_active=True
            )
            db.add(user)
            users.append(user)

        db.commit()
        print(f"Created {len(users)} users")

        print("Creating projects...")
        projects_data = [
            {
                "name": "Website Redesign",
                "description": "Complete redesign of company website with modern UI/UX",
                "is_private": False,
                "owner": users[1]
            },
            {
                "name": "Mobile App Development",
                "description": "Build iOS and Android mobile applications",
                "is_private": True,
                "owner": users[1]
            },
            {
                "name": "API Integration",
                "description": "Integrate third-party APIs for payment processing",
                "is_private": False,
                "owner": users[2]
            },
            {
                "name": "Database Migration",
                "description": "Migrate from MySQL to PostgreSQL",
                "is_private": True,
                "owner": users[0]
            },
            {
                "name": "Security Audit",
                "description": "Comprehensive security audit of all systems",
                "is_private": True,
                "owner": users[0]
            }
        ]

        projects = []
        for project_data in projects_data:
            project = Project(
                name=project_data["name"],
                description=project_data["description"],
                is_private=project_data["is_private"],
                owner=project_data["owner"]
            )
            project.members.append(project_data["owner"])

            for user in users[:3]:
                if user != project_data["owner"]:
                    project.members.append(user)

            db.add(project)
            projects.append(project)

        db.commit()
        print(f"Created {len(projects)} projects")

        print("Creating tasks...")
        tasks_data = [
            {
                "title": "Design homepage mockup",
                "description": "Create high-fidelity mockup for new homepage",
                "status": "done",
                "priority": "high",
                "project": projects[0],
                "assignee": users[2],
                "created_by": users[1].id
            },
            {
                "title": "Implement responsive navigation",
                "description": "Build mobile-friendly navigation component",
                "status": "in_progress",
                "priority": "high",
                "project": projects[0],
                "assignee": users[3],
                "created_by": users[1].id
            },
            {
                "title": "Set up Redux store",
                "description": "Configure Redux for state management",
                "status": "todo",
                "priority": "medium",
                "project": projects[1],
                "assignee": users[2],
                "created_by": users[1].id
            },
            {
                "title": "Design app icon",
                "description": "Create app icon for iOS and Android",
                "status": "todo",
                "priority": "low",
                "project": projects[1],
                "assignee": users[4],
                "created_by": users[1].id
            },
            {
                "title": "Integrate Stripe API",
                "description": "Add Stripe payment processing",
                "status": "in_progress",
                "priority": "high",
                "project": projects[2],
                "assignee": users[2],
                "created_by": users[2].id
            },
            {
                "title": "Test payment flows",
                "description": "End-to-end testing of payment processing",
                "status": "todo",
                "priority": "high",
                "project": projects[2],
                "assignee": users[3],
                "created_by": users[2].id
            },
            {
                "title": "Backup current database",
                "description": "Create full backup before migration",
                "status": "done",
                "priority": "high",
                "project": projects[3],
                "assignee": users[0],
                "created_by": users[0].id
            },
            {
                "title": "Write migration scripts",
                "description": "Develop scripts to migrate data schema",
                "status": "in_progress",
                "priority": "high",
                "project": projects[3],
                "assignee": users[2],
                "created_by": users[0].id
            },
            {
                "title": "Penetration testing",
                "description": "Conduct penetration testing on all endpoints",
                "status": "todo",
                "priority": "high",
                "project": projects[4],
                "assignee": users[0],
                "created_by": users[0].id
            },
            {
                "title": "Review authentication system",
                "description": "Audit authentication and authorization mechanisms",
                "status": "in_progress",
                "priority": "high",
                "project": projects[4],
                "assignee": users[1],
                "created_by": users[0].id
            }
        ]

        tasks = []
        for task_data in tasks_data:
            task = Task(
                title=task_data["title"],
                description=task_data["description"],
                status=task_data["status"],
                priority=task_data["priority"],
                project=task_data["project"],
                assignee=task_data["assignee"],
                created_by=task_data["created_by"]
            )
            db.add(task)
            tasks.append(task)

        db.commit()
        print(f"Created {len(tasks)} tasks")

        print("Creating comments...")
        comments_data = [
            {
                "content": "Great progress on this! The mockups look amazing.",
                "task": tasks[0],
                "author": users[1]
            },
            {
                "content": "Should we also consider tablet view for this?",
                "task": tasks[1],
                "author": users[2]
            },
            {
                "content": "I'll need access to the API documentation first.",
                "task": tasks[4],
                "author": users[2]
            },
            {
                "content": "Backup completed successfully. 2.3GB total.",
                "task": tasks[6],
                "author": users[0]
            }
        ]

        for comment_data in comments_data:
            comment = Comment(
                content=comment_data["content"],
                task=comment_data["task"],
                author=comment_data["author"]
            )
            db.add(comment)

        db.commit()
        print(f"Created {len(comments_data)} comments")

        print("\nDatabase seeding completed successfully!")
        print("\n" + "="*60)
        print("SEEDED USER CREDENTIALS")
        print("="*60)
        for user_data in users_data:
            print(f"Username: {user_data['username']:15} Password: {user_data['password']:15} Role: {user_data['role']}")
        print("="*60 + "\n")

    except Exception as e:
        print(f"Error during seeding: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
