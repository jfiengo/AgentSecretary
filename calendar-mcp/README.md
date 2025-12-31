# Calendar MCP Server

A FastAPI-based calendar scheduling backend for AI secretaries. This server provides both REST API endpoints and MCP (Model Context Protocol) tools for managing appointments, availability, and Google Calendar integration.

## Features

- **Appointment Management**: Book, cancel, and reschedule appointments
- **Availability Calculation**: Smart slot calculation based on business hours
- **Conflict Detection**: Database-level locking to prevent double-booking
- **Google Calendar Sync**: OAuth integration for bidirectional sync
- **MCP Tools**: 5 tools for AI assistant integration
- **iCal Export**: Export appointments to standard iCalendar format

## Tech Stack

- Python 3.11+
- FastAPI (async)
- PostgreSQL with SQLAlchemy 2.0 (async)
- MCP SDK for tool definitions
- Google Calendar API
- Fernet encryption for OAuth tokens

## Quick Start

### 1. Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Docker (optional, for local PostgreSQL)

### 2. Setup

```bash
# Clone and enter directory
cd calendar-mcp

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env
# Edit .env with your settings
```

### 3. Database Setup

Using Docker (recommended for development):

```bash
docker compose up -d
```

Or configure your own PostgreSQL and update `DATABASE_URL` in `.env`.

### 4. Run Migrations

```bash
# Generate initial migration
alembic revision --autogenerate -m "Initial tables"

# Apply migrations
alembic upgrade head
```

### 5. Start the Server

```bash
# Development mode
python -m app.main

# Or with uvicorn directly
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs available at: http://localhost:8000/docs

## MCP Server

Run the MCP server for AI assistant integration:

```bash
python run_mcp.py
```

### MCP Tools

| Tool | Description |
|------|-------------|
| `check_availability` | Get available time slots for a date |
| `book_appointment` | Book a new appointment |
| `cancel_appointment` | Cancel an existing appointment |
| `reschedule_appointment` | Move appointment to new time |
| `get_daily_schedule` | List all appointments for a date |

### Claude Desktop Configuration

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "calendar": {
      "command": "python",
      "args": ["/path/to/calendar-mcp/run_mcp.py"],
      "env": {
        "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/calendar_mcp"
      }
    }
  }
}
```

## REST API Endpoints

### Businesses

- `POST /businesses` - Create a business
- `GET /businesses/{id}` - Get business details
- `PATCH /businesses/{id}` - Update business
- `DELETE /businesses/{id}` - Delete business
- `GET /businesses` - List all businesses

### Availability

- `POST /businesses/{id}/availability-rules` - Set business hours
- `GET /businesses/{id}/availability-rules` - List availability rules
- `DELETE /businesses/{id}/availability-rules/{rule_id}` - Delete rule
- `GET /businesses/{id}/availability?date=YYYY-MM-DD` - Get available slots

### Appointments

- `POST /businesses/{id}/appointments` - Book appointment
- `GET /businesses/{id}/appointments` - List appointments
- `GET /appointments/{id}` - Get appointment details
- `PATCH /appointments/{id}` - Update appointment
- `POST /appointments/{id}/cancel` - Cancel appointment
- `POST /appointments/{id}/reschedule` - Reschedule appointment

### Google Calendar OAuth

- `GET /oauth/google/authorize?business_id=X` - Start OAuth flow
- `GET /oauth/google/callback` - OAuth callback
- `GET /oauth/google/status/{business_id}` - Check connection status
- `DELETE /oauth/google/disconnect/{business_id}` - Disconnect

## Example Usage

### Create a Business

```bash
curl -X POST http://localhost:8000/businesses \
  -H "Content-Type: application/json" \
  -d '{"name": "Junk Removal Pro", "timezone": "America/New_York"}'
```

### Set Business Hours

```bash
# Monday 9am-5pm
curl -X POST http://localhost:8000/businesses/1/availability-rules \
  -H "Content-Type: application/json" \
  -d '{"day_of_week": 0, "start_time": "09:00:00", "end_time": "17:00:00"}'
```

### Check Availability

```bash
curl "http://localhost:8000/businesses/1/availability?date=2024-01-15&duration_minutes=60"
```

### Book an Appointment

```bash
curl -X POST http://localhost:8000/businesses/1/appointments \
  -H "Content-Type: application/json" \
  -d '{
    "customer_email": "john@example.com",
    "customer_name": "John Doe",
    "service_type": "junk_removal",
    "start_time": "2024-01-15T10:00:00-05:00",
    "duration_minutes": 60,
    "notes": "Large couch pickup"
  }'
```

## Google Calendar Setup

1. Create a project in [Google Cloud Console](https://console.cloud.google.com/)
2. Enable the Google Calendar API
3. Create OAuth 2.0 credentials (Web application)
4. Add redirect URI: `http://localhost:8000/oauth/google/callback`
5. Copy Client ID and Secret to `.env`

## Project Structure

```
calendar-mcp/
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI application entry point
│   ├── config.py                   # Settings via pydantic-settings
│   ├── database.py                 # Async SQLAlchemy engine & session
│   │
│   ├── models/                     # SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   ├── business.py             # Business, AvailabilityRule
│   │   ├── customer.py             # Customer
│   │   ├── appointment.py          # Appointment, BlockedTime, enums
│   │   └── calendar_connection.py  # OAuth tokens for Google Calendar
│   │
│   ├── schemas/                    # Pydantic request/response models
│   │   ├── __init__.py
│   │   ├── business.py             # BusinessCreate, BusinessResponse, etc.
│   │   ├── availability.py         # AvailabilityRule schemas, AvailableSlot
│   │   └── appointment.py          # Appointment schemas, BookingResult
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── dependencies.py         # DB session dependency injection
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── businesses.py       # CRUD for businesses
│   │       ├── appointments.py     # Appointment booking/management
│   │       ├── availability.py     # Availability rules & slot queries
│   │       └── oauth.py            # Google OAuth flow endpoints
│   │
│   ├── mcp/
│   │   ├── __init__.py
│   │   └── server.py               # MCP tool definitions (stdio transport)
│   │
│   ├── services/                   # Core business logic
│   │   ├── __init__.py
│   │   ├── availability.py         # Slot calculation, conflict checking
│   │   ├── booking.py              # Booking with SELECT FOR UPDATE locking
│   │   └── google_calendar.py      # Push/pull sync with Google Calendar
│   │
│   └── utils/
│       ├── __init__.py
│       ├── encryption.py           # Fernet encryption for OAuth tokens
│       └── ical.py                 # iCalendar export/import helpers
│
├── alembic/                        # Database migrations
│   ├── env.py                      # Async migration environment
│   ├── script.py.mako              # Migration template
│   └── versions/                   # Generated migration files
│
├── tests/                          # Test suite
│   └── __init__.py
│
├── .env.example                    # Environment variable template
├── .gitignore
├── alembic.ini                     # Alembic configuration
├── docker-compose.yml              # PostgreSQL for local development
├── README.md
├── requirements.txt                # Python dependencies
└── run_mcp.py                      # Entry point for MCP stdio server
```

### Key Components

| Component | Purpose |
|-----------|---------|
| `app/main.py` | FastAPI app with lifespan, CORS, and router registration |
| `app/mcp/server.py` | MCP server with 5 scheduling tools for AI assistants |
| `app/services/availability.py` | Calculates available slots from rules minus conflicts |
| `app/services/booking.py` | Handles bookings with database-level race condition prevention |
| `app/services/google_calendar.py` | Bidirectional sync with Google Calendar API |

---

## Running the Application

### Option 1: Full Stack (REST API + Database)

```bash
# Terminal 1: Start PostgreSQL
cd calendar-mcp
docker compose up -d

# Terminal 2: Run the FastAPI server
cd calendar-mcp
source venv/bin/activate
python -m app.main
```

The REST API will be available at:
- **API**: http://localhost:8000
- **Interactive Docs (Swagger)**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Option 2: MCP Server Only (for AI Assistants)

```bash
cd calendar-mcp
source venv/bin/activate
python run_mcp.py
```

This starts the MCP server with stdio transport, suitable for integration with Claude Desktop or other MCP clients.

### Option 3: Both Simultaneously

You can run both the REST API and MCP server at the same time - they share the same database:

```bash
# Terminal 1: PostgreSQL
docker compose up -d

# Terminal 2: REST API
python -m app.main

# Terminal 3: MCP Server (for AI assistant)
python run_mcp.py
```

---

## Database Management

### Starting the Database

```bash
docker compose up -d
```

### Check Status

```bash
docker compose ps
```

### View Logs

```bash
docker compose logs postgres        # One-time view
docker compose logs -f postgres     # Follow/stream logs (Ctrl+C to exit)
```

### Stop the Database (keeps data)

```bash
docker compose stop
```

### Start Again (after stop)

```bash
docker compose start
```

### Shut Down Completely (keeps data)

```bash
docker compose down
```

### Shut Down AND Delete All Data (fresh start)

```bash
docker compose down -v
```

### Restart

```bash
docker compose restart
```

### Connect to Database Directly (for debugging)

```bash
# Open psql shell inside the container
docker compose exec postgres psql -U calendar_user -d calendar_mcp
```

Common psql commands once inside:
- `\dt` — list all tables
- `\d appointments` — describe a table's structure
- `SELECT * FROM businesses;` — run queries
- `\q` — quit

### Typical Daily Workflow

```bash
# Morning: start working
docker compose start
source venv/bin/activate
python -m app.main

# Evening: done for the day
# Press Ctrl+C to stop the Python server
docker compose stop

# Your data persists between sessions!
```

> **Note:** Data is stored in a Docker volume (`postgres_data`), so it survives `stop`, `start`, and even `down`. Only `down -v` deletes the data.

---

## Development

### Running Tests

```bash
pytest
```

### Generating Migrations

After modifying models:

```bash
# Generate a new migration
alembic revision --autogenerate -m "Add new field to appointment"

# Apply all pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

### Database Reset (Development Only)

```bash
# Stop and remove the database container
docker compose down -v

# Start fresh
docker compose up -d

# Run migrations
alembic upgrade head
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://...` |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID | (empty) |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret | (empty) |
| `GOOGLE_REDIRECT_URI` | OAuth callback URL | `http://localhost:8000/oauth/google/callback` |
| `SECRET_KEY` | Key for Fernet token encryption | (change in production!) |
| `HOST` | Server bind address | `0.0.0.0` |
| `PORT` | Server port | `8000` |
| `DEBUG` | Enable debug mode | `false` |

---

## Architecture

```
┌─────────────────┐     ┌─────────────────┐
│  AI Assistant   │     │   REST Client   │
│  (Claude, etc)  │     │   (curl, app)   │
└────────┬────────┘     └────────┬────────┘
         │                       │
         │ stdio                 │ HTTP
         │                       │
┌────────▼────────┐     ┌────────▼────────┐
│   MCP Server    │     │   FastAPI App   │
│  (run_mcp.py)   │     │   (main.py)     │
└────────┬────────┘     └────────┬────────┘
         │                       │
         └───────────┬───────────┘
                     │
          ┌──────────▼──────────┐
          │   Services Layer    │
          │  (availability.py,  │
          │   booking.py, etc)  │
          └──────────┬──────────┘
                     │
          ┌──────────▼──────────┐
          │     PostgreSQL      │
          │   (docker-compose)  │
          └─────────────────────┘
```

## License

MIT

