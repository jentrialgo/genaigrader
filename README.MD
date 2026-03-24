# GenAI Grader

GenAI Grader is a specialized web platform designed for the automated evaluation of academic examinations. The system leverages both local large language models (via Ollama) and remote providers through external APIs to facilitate batch grading, analytics, and comprehensive reporting.

## Core Features

* **Course and Examination Management**: Centralized tools to create and edit academic courses and associate specific exams with them.
* **Automated Grading Workflows**: Intelligent grading utilizing various language models to provide immediate feedback.
* **Batch Evaluation Engine**: Capabilities to run large-scale evaluations across multiple exams and models simultaneously.
* **Analytics and Reporting**: Detailed results visualization and the ability to download generated reports.
* **Model Integration**: Support for downloading local models through Ollama or integrating proprietary models via API keys.

---

## Deployment with Docker (Recommended)

The preferred method for running this application is through Docker, which ensures a consistent environment across different operating systems.

### Prerequisites

* Docker Desktop installed on the host machine.
* Ollama installed on the host machine (only if you plan to run Ollama outside Docker).

### Development Environment

The development configuration is optimized for local iteration, featuring live code reloading and a lightweight SQLite database.

1.  **Clone the Repository**:
    ```bash
    git clone <repository-url>
    cd genaigrader
    ```
2.  **Start the Development Containers**:
    ```bash
    docker compose -f Docker/docker-compose.dev.yml up --build
    ```
    * This service maps port 8000 on the host to port 8000 in the container.
    * Source code is mounted as a volume to allow real-time updates.
3.  **Create an Administrative Account**:
    ```bash
    docker compose -f Docker/docker-compose.dev.yml exec web uv run manage.py createsuperuser
    ```

### Production Environment

The production setup utilizes a multi-container architecture for increased stability and performance.

#### Environment Configuration

Before deploying to production, you **must** configure environment variables securely:

1.  **Create a Local `.env` File**:
    ```bash
    copy .env.example .env
    ```
    * Do **NOT** commit `.env` to version control (it is already in `.gitignore`).
    * The `.env` file contains sensitive credentials and should only exist on your deployment machine.

2.  **Update Sensitive Values**:
    Open `.env` and replace the placeholder values:
    ```dotenv
    POSTGRES_DB=genaigrader
    POSTGRES_USER=genai_user
    POSTGRES_PASSWORD=<strong-random-password>
    DATABASE_URL=postgres://genai_user:<strong-random-password>@db:5432/genaigrader
    OLLAMA_HOST=http://host.docker.internal:11434
    ```
    * Generate a strong, random password for `POSTGRES_PASSWORD` and update `DATABASE_URL` accordingly.
    * Never use the same password across environments.

#### Deploy Production Stack

1.  **Initialize Production Stack with Environment Variables**:
    ```bash
    docker compose --env-file .env -f Docker/docker-compose.prod.yml up -d --build
    ```
    * This environment deploys a PostgreSQL 15-alpine database container.
    * The database utilizes a persistent volume for data integrity.
    * Startup is managed by an entrypoint script that automatically applies migrations and collects static files.

2.  **Create an Administrative Account**:
    ```bash
    docker compose --env-file .env -f Docker/docker-compose.prod.yml exec web uv run manage.py createsuperuser
    ```

---

## 🤖 Ollama & Hardware Acceleration

* **CPU-Only by Default**: The containerized development Ollama runs on CPU, meaning lower performance.
* **Enabling GPU (NVIDIA)**: If the host has an NVIDIA GPU, they must install the NVIDIA Container Toolkit and uncomment the deploy block in `Docker/docker-compose.dev.yml`.
* **Running Ollama Outside Docker**: For maximum performance without Docker limits (like macOS Metal), they can run Ollama natively on the host and change `OLLAMA_HOST` in their `.env` file.

---

## Manual Installation (Host Machine)

For developers preferring a native installation, the project uses `uv` for dependency management via `pyproject.toml`.

1.  **Dependency Synchronization**:
    ```bash
    uv sync
    ```
2.  **Database and Static Asset Preparation**:
    ```bash
    uv run manage.py migrate
    uv run manage.py collectstatic
    ```
3.  **Start Development Server**:
    ```bash
    uv run manage.py runserver
    ```

---

## Pre-commit Workflow

To maintain code quality (linting and formatting), this project uses pre-commit hooks.

1.  **Initial Setup**:
    Run the following command to install the hooks. This configuration ensures hooks run correctly even if the virtual environment is not explicitly activated:
    ```bash
    uv run pre-commit install --install-hooks
    ```
2.  **Manual Execution**:
    To run all checks against the entire codebase manually:
    ```bash
    uv run pre-commit run --all-files
    ```
3.  **Automatic Checks**:
    Hooks will run automatically on every `git commit`. If a hook fails, correct the issues, restage the files, and commit again.

## Testing

Run the automated test suite to validate code functionality and ensure no regressions.

### Run Tests in Development Container

Execute tests inside the development container:

```bash
docker compose -f Docker/docker-compose.dev.yml exec web uv run python manage.py test
```

This command:
* Creates an isolated test database
* Executes all test files in the `genaigrader/tests/` directory
* Reports pass/fail status and coverage information

### Run Tests Manually (Host Machine)

If running natively on the host machine:

```bash
uv run python manage.py test
```

---

## Operational Commands

* **View Service Logs** (Development):
    ```bash
    docker compose -f Docker/docker-compose.dev.yml logs -f
    ```
* **View Service Logs** (Production):
    ```bash
    docker compose --env-file .env -f Docker/docker-compose.prod.yml logs -f
    ```
* **Stop and Remove Containers** (Development):
    ```bash
    docker compose -f Docker/docker-compose.dev.yml down
    ```
* **Stop and Remove Containers** (Production):
    ```bash
    docker compose --env-file .env -f Docker/docker-compose.prod.yml down
    ```
* **Dependency Updates**:
    If `pyproject.toml` is modified, regenerate the lockfile before rebuilding images:
    ```bash
    uv lock
    ```

## Project Structure

* `genaigrader/`: Core application logic, including models, views, and templates.
* `mi_web/`: Global Django project configurations and settings.
* `Docker/`: Containerization configurations, including Dockerfiles and Compose files.
* `static/`: Source directory for CSS and JavaScript assets.
* `scripts/`: Utility scripts for automated deployment and process management.

## license

MIT License. See [LICENSE](LICENSE) for details.
For questions or suggestions, open an issue or contact the author.