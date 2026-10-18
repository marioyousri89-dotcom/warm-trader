"""Claude connection. The swarm runs fine without it (pure-quant fallback); with an
ANTHROPIC_API_KEY set, Claude acts as the Chief Strategist and as the Improver."""
import json
import os


def parse_json(text):
    if not text:
        return None
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        return json.loads(text[a:b + 1])
    except Exception:
        return None


class LLM:
    def __init__(self, model, enabled=True):
        self.model = model
        self.client = None
        self.calls = 0
        self.errors = 0
        self.last_error = ""
        if enabled and os.environ.get("ANTHROPIC_API_KEY"):
            try:
                import anthropic
                self.client = anthropic.Anthropic()
            except Exception as e:          # package missing, etc.
                self.last_error = f"anthropic package: {e}"

    @property
    def on(self):
        return self.client is not None

    def ask_text(self, system, user, max_tokens=700):
        """Plain-text answer (used by the in-app chat). Returns None on failure."""
        if not self.client:
            return None
        try:
            r = self.client.messages.create(model=self.model, max_tokens=max_tokens, system=system,
                                            messages=[{"role": "user", "content": user}])
            self.calls += 1
            return "".join(b.text for b in r.content if getattr(b, "type", "") == "text").strip()
        except Exception as e:
            self.errors += 1
            self.last_error = str(e)[:200]
            return None

    def ask_json(self, system, user, max_tokens=1000):
        """Returns a parsed dict, or None on any failure (callers must handle None)."""
        if not self.client:
            return None
        try:
            r = self.client.messages.create(
                model=self.model, max_tokens=max_tokens, system=system,
                messages=[{"role": "user", "content": user}])
            self.calls += 1
            text = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
            out = parse_json(text)
            if out is None:
                self.errors += 1
                self.last_error = "reply was not valid JSON"
            return out
        except Exception as e:
            self.errors += 1
            self.last_error = str(e)[:200]
            return None
