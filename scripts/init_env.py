#!/usr/bin/env python3
"""Initialize environment variables and generate cryptographic keys."""

import os
import sys
from pathlib import Path
from cryptography.fernet import Fernet


def generate_fernet_key():
    """Generate a new Fernet encryption key."""
    key = Fernet.generate_key()
    return key.decode('utf-8')


def init_env():
    """Initialize .env file with generated values."""
    project_root = Path(__file__).parent.parent
    env_file = project_root / ".env"
    env_example = project_root / ".env.example"

    if env_file.exists():
        print(f"✓ .env already exists at {env_file}")
        return

    if not env_example.exists():
        print(f"✗ .env.example not found at {env_example}")
        sys.exit(1)

    # Read template
    template = env_example.read_text()

    # Generate keys
    fernet_key = generate_fernet_key()
    db_password = "changeme_in_production_12345"
    gitea_secret = "gitea_secret_key_change_me_12345"
    gitea_token = "your_gitea_api_token_here"

    # Replace placeholders
    env_content = template.replace(
        "FERNET_KEY=your-fernet-key-base64-encoded-here",
        f"FERNET_KEY={fernet_key}"
    )
    env_content = env_content.replace(
        "DB_PASSWORD=changeme_in_production",
        f"DB_PASSWORD={db_password}"
    )
    env_content = env_content.replace(
        "GITEA_SECRET_KEY=your-secret-key-change-me",
        f"GITEA_SECRET_KEY={gitea_secret}"
    )

    # Write .env file
    env_file.write_text(env_content)
    print(f"✓ Created .env at {env_file}")
    print(f"\n⚠️  IMPORTANT: Update these values in .env before deploying:")
    print(f"  - DB_PASSWORD")
    print(f"  - GITEA_TOKEN (generate in Gitea admin panel)")
    print(f"  - GITEA_SECRET_KEY")


def init_wheels_directory():
    """Create wheels directory for offline pip installation."""
    project_root = Path(__file__).parent.parent
    wheels_dir = project_root / "wheels"

    if wheels_dir.exists():
        print(f"✓ Wheels directory exists at {wheels_dir}")
        return

    wheels_dir.mkdir(exist_ok=True)
    print(f"✓ Created wheels directory at {wheels_dir}")
    print(f"\n⚠️  Download wheels for offline installation:")
    print(f"  pip download -r requirements.txt -d wheels/")


def init_directories():
    """Create necessary directories."""
    project_root = Path(__file__).parent.parent

    dirs = [
        project_root / "backups",
        project_root / "logs",
        project_root / "app" / "templates",
        project_root / "tests",
    ]

    for dir_path in dirs:
        dir_path.mkdir(exist_ok=True, parents=True)
        print(f"✓ Created/verified directory: {dir_path}")


def main():
    """Run all initialization tasks."""
    print("🚀 Initializing Air-Gapped Network Config Fortress (AGNCF)\n")

    try:
        print("📁 Setting up directories...")
        init_directories()
        print()

        print("🔑 Generating cryptographic keys...")
        init_env()
        print()

        print("📦 Setting up wheels directory...")
        init_wheels_directory()
        print()

        print("✅ Initialization complete!")
        print("\n📋 Next steps:")
        print("  1. Edit .env with your configuration")
        print("  2. Generate Gitea API token and update .env")
        print("  3. Run: docker compose up -d")
        print("  4. Access: http://localhost:8000/dashboard")

    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
