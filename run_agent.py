import openai, sys, os, json

model_id = os.environ.get('MODEL_ID', 'NOT SET')
api_key = os.environ.get('API_KEY', '')
instruction = os.environ.get('INSTRUCTION', '')

print(f"Using model: {model_id}")
print(f"Instruction: {instruction}")

if not api_key or len(api_key) < 10:
    print('CRITICAL: OPENCODE_API_KEY missing or invalid.')
    sys.exit(1)

client = openai.OpenAI(
    api_key=api_key,
    base_url="https://opencode.ai/zen/v1"
)

try:
    response = client.chat.completions.create(
        model=model_id,
        messages=[
            {
                'role': 'system',
                'content': (
                    'You are a senior software engineer. '
                    'When asked to write or change code, respond with ONLY the file contents. '
                    'Format your response as a JSON array like this:\n'
                    '[{"path": "src/main.rs", "content": "...file content..."}]\n'
                    'No explanation. No markdown. Only valid JSON.'
                )
            },
            {'role': 'user', 'content': instruction}
        ],
        temperature=0.8
    )
    if hasattr(response, 'choices') and response.choices:
        output = response.choices[0].message.content
        with open('agent_output.json', 'w') as f:
            f.write(output)
        print('Agent output saved.')
    else:
        print(f'Gateway Error: {response}')
        sys.exit(1)
except Exception as e:
    print(f'SDK Error: {e}')
    sys.exit(1)
