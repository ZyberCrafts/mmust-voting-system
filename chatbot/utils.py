import openai
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

openai.api_key = settings.OPENAI_API_KEY

def get_openai_response(user_message, context=None):
    """
    Get a response from OpenAI, using a system prompt that enforces relevance to the voting system.
    """
    if not settings.OPENAI_API_KEY:
        return None

    system_prompt = (
        "You are a helpful assistant for the MMUST University online voting system. "
        "You answer questions about elections, voting procedures, candidates, results, and related topics. "
        "If a user asks something completely unrelated, politely decline and redirect to voting topics. "
        "Keep answers concise and friendly. "
    )
    if context:
        system_prompt += f"\nCurrent context: {context}"

    try:
        response = openai.ChatCompletion.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            max_tokens=300,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        return None