from flask import Flask, request, jsonify
from query_law_pro import ask

app = Flask(__name__)

@app.route("/ask", methods=["POST"])
def ask_law():
    q = request.json.get("query", "")
    if not q:
        return jsonify({"error": "Query is required"}), 400
    answer = ask(q)
    return jsonify({"query": q, "answer": answer})

if __name__ == "__main__":
    app.run(port=8000, debug=True)