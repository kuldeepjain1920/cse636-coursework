import os
import sys
from openai import OpenAI

def main():
    # Fetch the credential injected by Jenkins
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable is missing.")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("Error: Please provide the log file path.")
        sys.exit(1)

    log_path = sys.argv[1]
    
    # Read the final 150 lines of logs to capture the error stack trace
    try:
        with open(log_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()
            log_tail = "".join(lines[-150:])
    except Exception as e:
        print(f"Failed to read logs: {e}")
        sys.exit(1)

    # Initialize the OpenAI client
    client = OpenAI(api_key=api_key)

    # Construct the AI Agent prompt
    prompt = f"""
    You are an expert DevOps AI Agent. A CI/CD build has just failed. 
    Analyze the following snippet of the failure log. Identify the root cause 
    and provide clear, concise, and actionable instructions to fix it.
    
    --- LOG SNIPPET ---
    {log_tail}
    --- END LOG SNIPPET ---
    """

    print("\n🤖 [AI Agent] Analyzing pipeline failure logs...")
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        
        analysis = response.choices[0].message.content
        print("\n================== AI AGENT FAILURE ANALYSIS ==================")
        print(analysis)
        print("===============================================================\n")

    except Exception as e:
        print(f"AI Agent failed to generate response: {e}")

if __name__ == "__main__":
    main()
