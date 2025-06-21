import openai
from ..config import settings
from loguru import logger

client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

async def ask_gpt(system_prompt, history, summary=None):
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if summary:
        messages.append({"role": "system", "content": f"Summary: {summary}"})
    for msg in history[-10:]:
        messages.append(msg)
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.7,
            max_tokens=512,
            stream=False
        )
        content = response.choices[0].message.content
        if content is not None:
            return content.strip()
        else:
            return "Извините, произошла ошибка при обращении к AI. Попробуйте позже."
    except Exception as e:
        logger.error(f"Ошибка OpenAI: {e}")
        return "Извините, произошла ошибка при обращении к AI. Попробуйте позже."
