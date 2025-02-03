import json

import openai

from src.utils.config import OPENAI_API_KEY

openai.api_key = OPENAI_API_KEY


def extract_product_attributes(query):
    """Extract structured attributes from a search query using OpenAI GPT-4."""
    prompt = f"""
    Given the search query: "{query}",
    extract the most relevant product attributes.
    Return JSON format.
    """

    response = openai.ChatCompletion.create(
        model="gpt-4", messages=[{"role": "user", "content": prompt}]
    )

    return json.loads(response["choices"][0]["message"]["content"])
