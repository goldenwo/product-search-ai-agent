import openai

from src.utils.config import OPENAI_API_KEY


class OpenAIService:
    """
    Handles interactions with OpenAI API for AI-powered query parsing.
    """

    def __init__(self):
        self.client = openai.OpenAI(api_key=OPENAI_API_KEY)  # Load API key

    def generate_response(self, prompt: str) -> str:
        """
        Sends a prompt to OpenAI and retrieves the response.

        Args:
            prompt (str): The input prompt for AI.

        Returns:
            str: The AI-generated response.
        """
        try:
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are an AI assistant."},
                    {"role": "user", "content": prompt},
                ],
            )
            return response["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"❌ OpenAI API error: {e}")
            return "{}"  # Return an empty JSON object in case of failure
