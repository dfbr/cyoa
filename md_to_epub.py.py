import os
import re
import subprocess

def preprocess_markdown_files(md_dir):
    md_files = sorted([f for f in os.listdir(md_dir) if f.endswith('.md')])
    for filename in md_files:
        path = os.path.join(md_dir, filename)
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Add anchor at the top if not present
        anchor = f'<a id="{filename[:-3]}"></a>\n'
        if not content.startswith(anchor):
            content = anchor + content
        # Convert [text](something.md) to [text](#something)
        content = re.sub(r'\]\(([^)]+)\.md\)', r'](#\1)', content)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
    return md_files

def create_epub(md_dir, output_epub, title="Adventure Story", cover_image=None, frontmatter=None, backmatter=None):
    md_files = sorted([os.path.join(md_dir, f) for f in os.listdir(md_dir) if f.endswith('.md')])
    if not md_files:
        print("No markdown files found!")
        return
    files_to_convert = []
    if frontmatter:
        files_to_convert.append(frontmatter)
    files_to_convert += md_files
    if backmatter:
        files_to_convert.append(backmatter)
    # Pandoc command
    cmd = [
        "pandoc",
        "--toc",
        "--metadata", f"title={title}",
        "-o", output_epub
    ]
    if cover_image:
        cmd += ["--epub-cover-image", cover_image]
    cmd += files_to_convert
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print(f"EPUB created: {output_epub}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Convert Markdown CYOA to EPUB with working links and cover.")
    parser.add_argument("md_dir", help="Directory containing .md files")
    parser.add_argument("output_epub", help="Output EPUB filename")
    parser.add_argument("--title", default="Adventure Story", help="Title for the EPUB")
    parser.add_argument("--cover_image", help="Path to cover image (jpg or png)")
    parser.add_argument("--frontmatter", help="Markdown file for front matter (title page, copyright, etc.)")
    parser.add_argument("--backmatter", help="Markdown file for back matter (about the author, etc.)")
    args = parser.parse_args()

    preprocess_markdown_files(args.md_dir)
    create_epub(
        args.md_dir,
        args.output_epub,
        args.title,
        cover_image=args.cover_image,
        frontmatter=args.frontmatter,
        backmatter=args.backmatter
    )