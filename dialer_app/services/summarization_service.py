# dialer_app/services/summarization_service.py
import os
from openai import OpenAI

def generate_summary(transcript: str, metadata: dict) -> str:
    """
    Generates a bullet-point summary (max 5 bullets) using the OpenAI API.
    The summary captures conversation context along with any contact details (phone numbers, emails, addresses)
    mentioned in the transcript or metadata.
    """
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    prompt = (
        "You are an assistant that summarizes call transcripts into concise bullet points. "
        "Generate a summary in bullet points (maximum 5 bullets) for the following conversation transcript. "
        "Include any details regarding phone numbers, email addresses, and physical addresses if mentioned, "
        "as well as the overall conversation context. Keep the summary brief and informative.\n\n"
        f"Transcript:\n{transcript}\n\n"
        #f"Metadata:\n{metadata}\n\n"
        "Summary (in bullet points):"
    )
    
    try:
        chat_completion = client.chat.completions.create(
            model="gpt-4o",  # or "gpt-3.5-turbo"
            messages=[
                {"role": "system", "content": "You are an assistant that creates concise summaries of call transcripts."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,
            max_tokens=150,
        )
        summary = chat_completion.choices[0].message.content.strip()
        return summary
    except Exception as e:
        print(f"[SummarizationService] Error generating summary: {e}")
        return "Summary generation failed."
