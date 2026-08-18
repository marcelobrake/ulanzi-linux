from scripts.check_repository_hygiene import check_entries, validate_content, validate_path


def test_project_paths_are_allowed() -> None:
    assert validate_path("src/ulanzi_linux/domain/device.py") == []
    assert validate_path(".gitleaks.toml") == []
    assert validate_path("README.md") == []


def test_local_and_unapproved_paths_are_rejected() -> None:
    assert validate_path(".mcp.json")
    assert validate_path(".playwright-mcp/page.yml")
    assert validate_path("notes.txt")


def test_credentials_are_rejected() -> None:
    private_key = "-----BEGIN " + "PRIVATE KEY-----\nnot-a-real-key"
    aws_key = "AKIA" + "A" * 16
    assert "private key" in validate_content(private_key.encode())
    assert "AWS access key" in validate_content(aws_key.encode())


def test_environment_dumps_and_personal_paths_are_rejected() -> None:
    home = "/" + "home/alice"
    environment = f"HOME={home}\nPATH=/bin\nPWD={home}/project\nUSER=alice\n".encode()
    findings = validate_content(environment)
    assert "shell/session environment dump" in findings
    assert "personal absolute home path" in findings


def test_check_entries_reports_path_and_content_findings() -> None:
    credential = ("pass" + "word=not-a-real-password").encode()
    failures = check_entries([("notes.txt", credential)])
    assert failures == [
        "notes.txt: top-level file is not explicitly approved, assigned credential"
    ]
