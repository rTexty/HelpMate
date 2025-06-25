import openai
from ..config import settings
from loguru import logger

client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

async def ask_gpt(system_prompt: str, history: list, summary: str | None = None):
    messages = [{"role": "system", "content": system_prompt}]
    
    if summary:
        messages.append({"role": "system", "content": f"Вот краткое резюме предыдущих разговоров с этим пользователем, используй его для контекста: {summary}"})

    messages.extend(history)

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.7,
            max_tokens=1000,
            stream=False
        )
        content = response.choices[0].message.content
        if content:
            return content.strip()
        return "К сожалению, я не могу дать ответ на это. Попробуйте переформулировать."
    except Exception as e:
        logger.error(f"Ошибка OpenAI: {e}")
        return "Извините, произошла ошибка при обращении к AI. Попробуйте позже."
