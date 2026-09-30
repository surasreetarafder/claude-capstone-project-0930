# Runs the real app.main() with a fake uploaded file and records every Claude request.
import io, os, sys
sys.path.insert(0, os.environ["APP_DIR"])
import streamlit as st
import anthropic
import app

class FakeUpload(io.BytesIO):
    def __init__(self, path):
        data = open(path, "rb").read()
        super().__init__(data)
        self.name, self.size = os.path.basename(path), len(data)

# TEST_FILE can hold several paths separated by ";" (multi-document upload).
st.file_uploader = lambda *a, **k: [FakeUpload(p) for p in os.environ["TEST_FILE"].split(";")]

RealClient = getattr(anthropic, '_original_client', anthropic.Anthropic)
anthropic._original_client = RealClient
class RecordingClient:
    def __init__(self, *a, **k):
        self._real = RealClient(*a, **k)
        self.messages = self
    def create(self, **kwargs):
        st.session_state.setdefault("_requests", []).append(kwargs)
        return self._real.messages.create(**kwargs)
app.anthropic.Anthropic = RecordingClient

app.main()
