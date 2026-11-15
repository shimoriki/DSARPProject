from dsarp.models.providers import Completion


class Scripted:
    """A fake model that answers with the given texts in order and records every prompt."""

    def __init__(self, *texts):
        self.texts, self.prompts = list(texts), []

    def generate(self, prompt, **_):
        self.prompts.append(prompt)
        return Completion(text=self.texts.pop(0))
