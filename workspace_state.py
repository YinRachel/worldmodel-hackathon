"""Local handoff between room clearing and furniture selection."""
import json
from pathlib import Path
from threading import Lock
ROOT = Path(__file__).resolve().parent
LOCK = Lock()
PATH = ROOT / 'outputs/workspace-state.json'
def read_state():
    with LOCK:
        return json.loads(PATH.read_text()) if PATH.exists() else {}
def update_state(**changes):
    with LOCK:
        state=json.loads(PATH.read_text()) if PATH.exists() else {}
        state.update(changes)
        PATH.parent.mkdir(exist_ok=True)
        temp=PATH.with_suffix('.tmp')
        temp.write_text(json.dumps(state,indent=2))
        temp.replace(PATH)
        return state
