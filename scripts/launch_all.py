"""
launch_all.py — unified runner for Pakistan Law Assistant
Starts:
  1️⃣ Flask view_server.py  (port 5002)
  2️⃣ Streamlit ui_app.py   (default Streamlit port)
Keeps both running until you close the terminal.
"""

import subprocess, sys, os, time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- helper to run a command in a new window ---
def run_process(title, cmd):
    if os.name == "nt":  # Windows
        return subprocess.Popen(
            ["start", "cmd", "/k", f"title {title} && {cmd}"],
            shell=True
        )
    else:  # Linux / macOS
        return subprocess.Popen(cmd, shell=True)

# --- start Flask view server ---
flask_cmd = f"{sys.executable} {os.path.join(BASE_DIR, 'view_server.py')}"
print("🚀 Starting Flask viewer (port 5002)...")
run_process("Flask Viewer 5002", flask_cmd)
time.sleep(2)  # give Flask time to start

# --- start Streamlit app ---
ui_path = os.path.join(BASE_DIR, "ui_app.py")
streamlit_cmd = f"streamlit run {ui_path}"
print("⚖️  Launching Streamlit Pakistan Law Assistant...")
run_process("Streamlit UI", streamlit_cmd)

print("\n✅ Both servers are starting.\n"
      "• Flask Viewer → http://127.0.0.1:5002/view?law=...&section=...\n"
      "• Streamlit UI → usually http://localhost:8501\n"
      "\nKeep both terminal windows open.")