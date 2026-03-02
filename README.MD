# GenAI Grader

GenAI Grader is a web platform for automated exam grading using both local (Ollama) and remote (external API) language models. It allows you to manage courses, exams, and perform batch evaluations, providing analytics and downloadable reports.

## Features

- **Course and Exam Management:** Create, edit, and delete courses. Assign exams to courses.
- **Automated Grading:** Select language models (local or external) to automatically grade exams.
- **Batch Evaluations:** Run batch evaluations on multiple exams and models.
- **Analytics and Reports:** View results, download reports, and access detailed analytics.
- **Model Management:** Add external models via API or download local models from Ollama.
- **Modern Interface:** Responsive dark UI with custom styles in `/static/css/`.

## Installation

1. **Clone the repository**
   ```sh
   git clone <your-repo-url>
   cd genaigrader
   ```

2. **Install dependencies and Ollama**
   To install `uv`, run:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
   Then, install dependencies:
   ```sh
   uv pip install -r requirements.txt
   ```

   To use local models, install [Ollama](https://ollama.com/) and start the service:
   ```sh
   # On Linux:
   curl -fsSL https://ollama.com/install.sh | sh
   ollama serve
   ```
   *Note: Remember to pull the models you want to use (e.g., `ollama pull llama3`).*

3. **Configure environment variables**
   Copy `.env.example` to `.env`. (Note: The `start_genaigrader.sh` script specifically looks for `.env.django`).
   ```sh
   cp .env.example .env
   ```

4. **Run migrations and collect static files**
   ```sh
   uv run manage.py migrate
   uv run manage.py collectstatic
   ```

5. **Start the server** (locally on port 8000)
   ```sh
   uv run manage.py runserver
   ```
   Or use the automated scripts in `scripts/`:
   ```sh
   bash scripts/start_genaigrader.sh
   ```
   *Note: The script uses port 9898 and expects several configurations. Check `scripts/README.md` for more details.*

## Usage

1. Access the app at `http://localhost:8000/`.
2. Register or log in.
3. Create courses and upload exams.
4. Manage models in the "Models" section.
5. Run batch evaluations from "Batch Evaluations".
6. View results and analytics in "Analysis".

## Project Structure

- `genaigrader/`: Main app logic (models, views, services, templates).
- `mi_web/`: Django configuration (settings, urls, wsgi/asgi).
- `static/`: Static files (CSS, JS).
- `uploaded_files/`: User-uploaded files.
- `scripts/`: Utility scripts for development/deployment.

## Useful Scripts

- `scripts/start_genaigrader.sh`: Start the app with Gunicorn and Ollama in tmux.
- `scripts/stop_genaigrader.sh`: Stop the app and related processes.

## License

MIT License. See [LICENSE](LICENSE) for details.

---

For questions or suggestions, open an issue or contact the author.