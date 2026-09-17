from flask import Flask, send_from_directory
from flask_cors import CORS

from routes.auth import auth_bp
from routes.projects import projects_bp
from routes.columns import columns_bp
from routes.tasks import tasks_bp

app = Flask(__name__)

# Allow the frontend (served separately as static files) to call this API.
# Tighten origins= to your actual deployed frontend URL before submitting.
CORS(app, origins="*", supports_credentials=True)

app.register_blueprint(auth_bp)
app.register_blueprint(projects_bp)
app.register_blueprint(columns_bp)
app.register_blueprint(tasks_bp)


@app.route("/")
def serve_index():
    return send_from_directory(".", "index.html")


@app.route("/board.html")
def serve_board():
    return send_from_directory(".", "board.html")


@app.route("/api/health", methods=["GET"])
def health():
    return {"status": "ok"}, 200


# Without these, an unhandled error or a wrong URL returns Flask's default
# HTML error page — which breaks api.js's `response.json()` call on the
# frontend. Keeping every response as JSON means errors always surface as
# a readable message.
@app.errorhandler(404)
def not_found(e):
    return {"error": "That endpoint doesn't exist"}, 404


@app.errorhandler(500)
def server_error(e):
    return {"error": "Something went wrong on the server"}, 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)