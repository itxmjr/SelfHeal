from __future__ import annotations

import re
from typing import Any, List, Optional

import yaml
from ..config import save_life_model, load_life_model
from ..llm import get_llm_with_fallback
from ..obsidian import save_interview_to_obsidian
from .prompts import SYSTEM_PROMPT, FOLLOW_UP_PROMPT, REGENERATE_PROMPT

class InterviewSession:
    def __init__(self, regenerate: bool = False):
        self.llm = get_llm_with_fallback(task_type="interview")
        self.messages: List[dict[str, str]] = []
        self.is_complete = False
        self.model: Optional[dict[str, Any]] = None

        if regenerate:
            current = load_life_model()
            if current:
                current_yaml = yaml.dump(current, default_flow_style=False)
                system_msg = REGENERATE_PROMPT.format(current_model=current_yaml)
            else:
                system_msg = SYSTEM_PROMPT
        else:
            system_msg = SYSTEM_PROMPT

        self.messages.append({"role": "system", "content": system_msg})

    def get_initial_question(self) -> str:
        response = self.llm.chat(self.messages, temperature=0.7)
        assistant_msg = response.content
        self.messages.append({"role": "assistant", "content": assistant_msg})
        return self._clean_message(assistant_msg)

    def respond(self, user_input: str) -> str:
        self.messages.append({"role": "user", "content": user_input})
        
        if len(self.messages) > 30:
            self.messages = [self._compress_history(self.messages)]

        response = self.llm.chat(self.messages, temperature=0.7)
        assistant_msg = response.content
        self.messages.append({"role": "assistant", "content": assistant_msg})

        if "[INTERVIEW_COMPLETE]" in assistant_msg:
            self.model = self._extract_yaml(assistant_msg)
            if self.model:
                self.is_complete = True
                save_life_model(self.model)
                save_interview_to_obsidian(self.messages, self.model)
                return "INTERVIEW_COMPLETE"
            else:
                self.messages.append({"role": "user", "content": "Please provide the YAML life model again, making sure it is valid YAML."})
                return self.respond("Please retry YAML generation.")

        return self._clean_message(assistant_msg)

    def _clean_message(self, text: str) -> str:
        return text.replace("[INTERVIEW_COMPLETE]", "").strip()

    def _extract_yaml(self, text: str) -> dict[str, Any] | None:
        yaml_match = re.search(r"```yaml\s*\n(.*?)```", text, re.DOTALL)
        if yaml_match:
            try:
                return yaml.safe_load(yaml_match.group(1))
            except yaml.YAMLError:
                pass

        yaml_match = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
        if yaml_match:
            try:
                return yaml.safe_load(yaml_match.group(1))
            except yaml.YAMLError:
                pass

        return None

    def _compress_history(self, messages: list[dict[str, str]]) -> dict[str, str]:
        history_text = ""
        for m in messages:
            role = m["role"]
            content = m["content"][:300]
            history_text += f"{role}: {content}\n"
        return {
            "role": "system",
            "content": FOLLOW_UP_PROMPT.format(history=history_text),
        }
