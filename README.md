# CollabSpace - Project Collaboration Platform (Vulnerable Web app for testing)

A modern project collaboration platform built with FastAPI, PostgreSQL, and Jinja2 templates.

## Features

- **User Management**: Registration, login, role-based access control
- **Project Management**: Create, update, delete projects with privacy settings
- **Task Tracking**: Kanban-style task management with priorities and status
- **File Uploads**: Upload and manage project files
- **Comments**: Collaborate through task comments
- **Admin Dashboard**: Administrative tools and analytics
- **Real-time Analytics**: Project and task statistics

## Technology Stack

- **Backend**: Python FastAPI
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Authentication**: JWT-based authentication
- **Frontend**: Jinja2 templates with vanilla JavaScript
- **Deployment**: Docker & Docker Compose

## Quick Start

### Prerequisites

- Docker
- Docker Compose

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd Acs_vulnerable_web_app
```

2. Start the application:
```bash
docker compose up --build
```

3. Access the application:
```
http://localhost:8000
```

The application will automatically:
- Create database tables
- Seed initial data
- Start the web server

## Default User Accounts

After seeding, the following accounts are available:

| Username | Password   | Role    |
|----------|------------|---------|
| admin    | Admin123!  | admin   |
| alice    | Alice123!  | manager |
| bob      | Bob123!    | member  |
| charlie  | Charlie123!| member  |
| diana    | Diana123!  | member  |

## Application Structure

```
Acs_vulnerable_web_app/
├── app/
│   ├── routers/
│   │   ├── auth.py          # Authentication endpoints
│   │   ├── projects.py      # Project management
│   │   ├── tasks.py         # Task management
│   │   ├── files.py         # File upload/download
│   │   ├── comments.py      # Comment system
│   │   ├── admin.py         # Admin dashboard
│   │   └── internal.py      # Internal API endpoints
│   ├── templates/           # HTML templates
│   ├── static/             # CSS and JavaScript
│   ├── models.py           # Database models
│   ├── schemas.py          # Pydantic schemas
│   ├── auth.py             # Authentication utilities
│   ├── config.py           # Configuration settings
│   ├── database.py         # Database connection
│   ├── dependencies.py     # FastAPI dependencies
│   └── main.py            # Application entry point
├── uploads/               # File upload directory
├── seed_data.py          # Database seeding script
├── requirements.txt      # Python dependencies
├── Dockerfile           # Docker configuration
├── docker-compose.yml   # Docker Compose configuration
└── README.md           # This file
```

## API Endpoints

### Authentication
- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - User login
- `POST /api/auth/logout` - User logout
- `GET /api/auth/me` - Get current user info
- `POST /api/auth/reset-password` - Request password reset
- `POST /api/auth/confirm-reset` - Confirm password reset

### Projects
- `GET /api/projects` - List all projects
- `POST /api/projects` - Create new project
- `GET /api/projects/{id}` - Get project details
- `PUT /api/projects/{id}` - Update project
- `DELETE /api/projects/{id}` - Delete project
- `GET /api/projects/search` - Search projects
- `POST /api/projects/{id}/members` - Add project member

### Tasks
- `GET /api/tasks` - List tasks
- `POST /api/tasks` - Create new task
- `GET /api/tasks/{id}` - Get task details
- `PUT /api/tasks/{id}` - Update task
- `DELETE /api/tasks/{id}` - Delete task
- `POST /api/tasks/{id}/transfer` - Transfer task ownership

### Files
- `POST /api/files/upload` - Upload file
- `GET /api/files/{id}` - Get file info
- `GET /api/files/{id}/download` - Download file
- `DELETE /api/files/{id}` - Delete file
- `POST /api/files/process` - Process file

### Comments
- `GET /api/comments` - List comments for a task
- `POST /api/comments` - Create comment
- `GET /api/comments/{id}` - Get comment details
- `DELETE /api/comments/{id}` - Delete comment

### Admin
- `GET /api/admin/users` - List all users
- `PUT /api/admin/users/{id}` - Update user
- `DELETE /api/admin/users/{id}` - Delete user
- `GET /api/admin/stats` - Get system statistics
- `POST /api/admin/fetch-url` - Fetch external URL (admin tool)
- `POST /api/admin/execute-query` - Execute custom query (admin tool)

### Internal
- `GET /api/internal/health` - Health check
- `GET /api/internal/debug` - Debug information
- `POST /api/internal/update-config` - Update configuration
- `POST /api/internal/create-admin` - Create emergency admin
- `POST /api/internal/backup` - Create database backup
- `GET /api/internal/logs` - Get application logs
- `GET /api/internal/sessions` - List active sessions

## Configuration

Key configuration options in `app/config.py`:

- `DATABASE_URL`: PostgreSQL connection string
- `SECRET_KEY`: JWT secret key
- `ACCESS_TOKEN_EXPIRE_MINUTES`: JWT token expiration
- `DEBUG`: Enable debug mode
- `UPLOAD_DIR`: File upload directory
- `MAX_UPLOAD_SIZE`: Maximum file upload size
- `CORS_ORIGINS`: CORS allowed origins

## Development

### Running Tests

```bash
pytest
```

### Database Migrations

The application automatically creates tables on startup. To reset the database:

```bash
docker compose down -v
docker compose up --build
```

### Viewing Logs

```bash
docker compose logs -f web
```

## License

Internal use only.
