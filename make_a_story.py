import openai
import argparse
import os
import re
import logging
import string
import sys
import time

def sanitize_filename(name):
    return re.sub(r'[^a-zA-Z0-9_\-]', '_', name)[:40]

def save_section(story_dir, section_id, story_text, choices, metadata=None):
    # Remove "section_" prefix from filename
    clean_id = section_id.replace("section_", "", 1)
    filename = os.path.join(story_dir, f"{clean_id}.md")
    with open(filename, "w", encoding="utf-8") as f:
        if metadata:
            f.write('<!--\n')
            f.write(str(metadata))
            f.write('\n-->\n\n')
        f.write(story_text.strip() + "\n\n")
        f.write("## Choices\n")
        for idx, choice in enumerate(choices):
            suffix = string.ascii_lowercase[idx]
            next_section = f"{section_id}_{suffix}".replace("section_", "", 1)
            f.write(f"- [{choice}]({next_section}.md)\n")
    logging.info(f"Saved: {filename}")

def build_prompt(story_so_far, last_choice, section_number, system_message, user_message):
    prompt = (
        f"{system_message}\n\n"
        f"{user_message}\n\n"
        f"Story so far:\n{story_so_far}\n\n"
        f"The reader just chose: \"{last_choice}\"\n"
        f"This is section number {section_number}.\n\n"
        "Write the next section of the story (do not include choices in the story text).\n"
        "Then, provide a list of 2-4 choices for what the reader can do next, each as a plain string (not markdown links).\n\n"
        "Format your response as:\n"
        "Story:\n"
        "<the story text>\n\n"
        "Choices:\n"
        "- <choice 1>\n"
        "- <choice 2>\n"
        "- <choice 3>\n"
    )
    return prompt

def parse_gpt_response(response):
    # Extract story and choices from the GPT response
    story_match = re.search(r"Story:\s*(.*?)\s*Choices:", response, re.DOTALL | re.IGNORECASE)
    choices_match = re.findall(r"- (.+)", response)
    story = story_match.group(1).strip() if story_match else ""
    choices = [c.strip() for c in choices_match]
    return story, choices

def generate_section(prompt, model, max_tokens, dry_run=False, api_key=None, max_retries=5, timeout=60):
    if dry_run:
        logging.info("DRY RUN: Would send prompt to OpenAI:\n%s", prompt)
        return (
            "Story:\nThis is a dry run. No content generated.\n\nChoices:\n- Choice 1\n- Choice 2"
        )
    client = openai.OpenAI(api_key=api_key)
    for attempt in range(1, max_retries + 1):
        try:
            logging.info(f"Sending prompt to OpenAI API (attempt {attempt}):\n{prompt}")
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.7,
                timeout=timeout
            )
            content = response.choices[0].message.content
            logging.info("Received response from OpenAI API:\n%s", content)
            return content
        except Exception as e:
            logging.warning(f"OpenAI API call failed on attempt {attempt}: {e}")
            if attempt == max_retries:
                logging.error("Max retries reached. Exiting script.")
                sys.exit(1)
            else:
                time.sleep(2)  # brief pause before retrying

def recursive_generate(
    story_dir,
    story_title,
    section_id,
    history,
    model,
    system_message,
    user_message,
    max_tokens,
    depth,
    max_depth,
    dry_run=False,
    api_key=None,
    resume=False
):
    import string

    if depth > max_depth:
        return

    filename = os.path.join(story_dir, f"{section_id}.md")
    if resume and os.path.exists(filename):
        logging.info(f"Section {section_id} already exists, skipping generation but recursing into children.")
        # Extract choices from the file and recurse into children
        choices = extract_choices_from_file(filename)
        if not choices:
            logging.info(f"Ending detected at {section_id} (no choices in file).")
            return
        for idx, choice_text in enumerate(choices):
            suffix = string.ascii_lowercase[idx]
            next_section_id = f"{section_id}_{suffix}"
            # We don't have the story text here, but that's OK for context
            new_history = history + [("", choice_text)]
            recursive_generate(
                story_dir, story_title, next_section_id, new_history, model, system_message,
                user_message, max_tokens, depth+1, max_depth, dry_run, api_key, resume
            )
        return

    # Build story so far and last choice
    story_so_far = ""
    last_choice = ""
    for idx, (section, choice) in enumerate(history):
        story_so_far += f"Section {idx+1}:\n{section.strip()}\n"
        if choice:
            story_so_far += f"The reader chose: {choice}\n"
        last_choice = choice

    section_number = len(history) + 1

    # Build prompt
    prompt = build_prompt(
        story_so_far=story_so_far,
        last_choice=last_choice,
        section_number=section_number,
        system_message=system_message,
        user_message=user_message
    )

    # Generate section
    response = generate_section(prompt, model, max_tokens, dry_run=dry_run, api_key=api_key)
    story_text, choices = parse_gpt_response(response)

    # Save section
    metadata = {
        "section_id": section_id,
        "depth": depth,
        "choices_taken": [c for _, c in history],
        "parent": history[-1][1] if history else None
    }
    save_section(story_dir, section_id, story_text, choices, metadata=metadata)

    # If no choices, stop recursion (end of story)
    if not choices:
        logging.info(f"Ending detected at {section_id}.")
        return

    # Recursively generate next sections for each choice
    for idx, choice_text in enumerate(choices):
        suffix = string.ascii_lowercase[idx]
        next_section_id = f"{section_id}_{suffix}"
        new_history = history + [(story_text, choice_text)]
        recursive_generate(
            story_dir, story_title, next_section_id, new_history, model, system_message,
            user_message, max_tokens, depth+1, max_depth, dry_run, api_key, resume
        )

def extract_choices_from_file(filename):
    choices = []
    in_choices = False
    with open(filename, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip() == "## Choices":
                in_choices = True
                continue
            if in_choices:
                match = re.match(r"- \[(.*?)\]", line)
                if match:
                    choices.append(match.group(1))
                elif line.strip() == "" or not line.startswith("- ["):
                    break
    return choices

def main():
    parser = argparse.ArgumentParser(description="ChatGPT Choose Your Own Adventure Story Generator")
    parser.add_argument('--api_key', required=True, help='Your OpenAI API key')
    parser.add_argument('--model', default='gpt-3.5-turbo', help='OpenAI model name (default: gpt-3.5-turbo)')
    parser.add_argument('--system_message_file', required=True, help='File containing the system prompt for the assistant')
    parser.add_argument('--max_tokens', type=int, default=2000, help='Maximum tokens in the response (default: 2000)')
    parser.add_argument('--max_depth', type=int, default=20, help='Maximum depth of story branches (default: 20)')
    parser.add_argument('--title', required=True, help='Title of the story')
    parser.add_argument('--user_message_file', required=True, help='File containing the user message for the initial prompt')
    parser.add_argument('--dry_run', action='store_true', help='Simulate generation without calling the API')
    parser.add_argument('--log_file', default='story_generation.log', help='Log file name')
    parser.add_argument('--resume', action='store_true', help='Resume story generation, skipping existing sections')
    args = parser.parse_args()

    logging.basicConfig(
        filename=args.log_file,
        level=logging.INFO,
        format='%(asctime)s %(levelname)s: %(message)s'
    )

    # Read system message from file
    with open(args.system_message_file, "r", encoding="utf-8") as f:
        system_message = f.read().strip()

    # Read user message from file
    with open(args.user_message_file, "r", encoding="utf-8") as f:
        user_message = f.read().strip()

    story_dir = sanitize_filename(args.title)
    os.makedirs(story_dir, exist_ok=True)

    recursive_generate(
        story_dir=story_dir,
        story_title=args.title,
        section_id="section_1",
        history=[],
        model=args.model,
        system_message=system_message,
        user_message=user_message,
        max_tokens=args.max_tokens,
        depth=1,
        max_depth=args.max_depth,
        dry_run=args.dry_run,
        api_key=args.api_key,
        resume=args.resume
    )

if __name__ == "__main__":
    main()