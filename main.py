from dotenv import load_dotenv

from clinical_trials_guru import guru_main
from llm import get_provider

load_dotenv()

if __name__ == "__main__":
    guru_main(get_provider("anthropic"))
