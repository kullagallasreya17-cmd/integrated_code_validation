import json
import os
import subprocess
import tempfile
from typing import List, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field


app = FastAPI(
    title="Security Agent",
    description="Security vulnerability detection service",
    version="1.2.0",
)

GITLEAKS_PATH = os.getenv("GITLEAKS_PATH", "gitleaks")
MAX_CODE_SIZE = 200_000
MAX_FILENAME_LENGTH = 255


class CodeRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=MAX_CODE_SIZE)
    filename: str = Field(default="main.py", min_length=1, max_length=MAX_FILENAME_LENGTH)


class SecurityFinding(BaseModel):
    type: str
    severity: str
    file: str
    line: Optional[int] = None
    description: str
    evidence: Optional[str] = None
    owasp: Optional[str] = None
    cwe: Optional[str] = None
    recommendation: Optional[str] = None


class SecurityResponse(BaseModel):
    status: str
    filename: str
    total_findings: int
    findings: List[SecurityFinding]


@app.get("/")
def root():
    return {"service": "Security Agent", "status": "running", "version": "1.2.0"}


@app.get("/health")
def health():
    return {"status": "healthy", "service": "security-agent"}


def get_safe_filename(filename: str) -> str:
    return os.path.basename(filename.strip()) or "main.py"


def get_owasp_mapping(cwe_id: Optional[int]) -> Optional[str]:
    mapping = {
        22: "A01:2021 - Broken Access Control",
        23: "A01:2021 - Broken Access Control",
        35: "A01:2021 - Broken Access Control",
        284: "A01:2021 - Broken Access Control",
        285: "A01:2021 - Broken Access Control",
        352: "A01:2021 - Broken Access Control",
        639: "A01:2021 - Broken Access Control",
        259: "A07:2021 - Identification and Authentication Failures",
        287: "A07:2021 - Identification and Authentication Failures",
        306: "A07:2021 - Identification and Authentication Failures",
        522: "A07:2021 - Identification and Authentication Failures",
        798: "A07:2021 - Identification and Authentication Failures",
        261: "A02:2021 - Cryptographic Failures",
        295: "A02:2021 - Cryptographic Failures",
        311: "A02:2021 - Cryptographic Failures",
        312: "A02:2021 - Cryptographic Failures",
        319: "A02:2021 - Cryptographic Failures",
        326: "A02:2021 - Cryptographic Failures",
        327: "A02:2021 - Cryptographic Failures",
        78: "A03:2021 - Injection",
        79: "A03:2021 - Injection",
        89: "A03:2021 - Injection",
        90: "A03:2021 - Injection",
        91: "A03:2021 - Injection",
        94: "A03:2021 - Injection",
        643: "A03:2021 - Injection",
        200: "A04:2021 - Insecure Design",
        209: "A04:2021 - Insecure Design",
        256: "A04:2021 - Insecure Design",
        16: "A05:2021 - Security Misconfiguration",
        434: "A05:2021 - Security Misconfiguration",
        548: "A05:2021 - Security Misconfiguration",
        942: "A05:2021 - Security Misconfiguration",
        601: "A06:2021 - Vulnerable and Outdated Components",
        110: "A06:2021 - Vulnerable and Outdated Components",
        362: "A09:2021 - Security Logging and Monitoring Failures",
        778: "A09:2021 - Security Logging and Monitoring Failures",
        611: "A10:2021 - Server-Side Request Forgery",
        918: "A10:2021 - Server-Side Request Forgery",
        494: "A08:2021 - Software and Data Integrity Failures",
        502: "A08:2021 - Software and Data Integrity Failures",
        829: "A08:2021 - Software and Data Integrity Failures",
        1104: "A08:2021 - Software and Data Integrity Failures",
    }
    return mapping.get(cwe_id)


def normalize_severity(severity: Optional[str]) -> str:
    severity = (severity or "INFO").upper()
    return severity if severity in {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"} else "INFO"


def extract_cwe(value) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, list):
        value = value[0] if value else None
    if not value:
        return None
    value = str(value)
    return value if "CWE-" in value else f"CWE-{value}" if value.isdigit() else value


def get_cwe_id(cwe: Optional[str]) -> Optional[int]:
    try:
        return int(cwe.replace("CWE-", "").strip()) if cwe else None
    except ValueError:
        return None


def deduplicate_findings(findings: List[SecurityFinding]) -> List[SecurityFinding]:
    unique, seen = [], set()
    for finding in findings:
        key = (finding.file, finding.line, finding.cwe, finding.type, finding.description)
        if key not in seen:
            seen.add(key)
            unique.append(finding)
    return unique


def run_bandit(code: str, filename: str) -> List[SecurityFinding]:
    findings = []
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        temp_path = f.name

    try:
        result = subprocess.run(
            ["bandit", "-f", "json", "-q", temp_path],
            capture_output=True, text=True, timeout=30
        )

        if not result.stdout.strip():
            if result.returncode != 0:
                findings.append(SecurityFinding(
                    type="ScannerError", severity="HIGH", file=filename,
                    description=f"Bandit scan failed: {result.stderr.strip()}",
                    recommendation="Check the Bandit installation and scanner configuration."
                ))
            return findings

        for issue in json.loads(result.stdout).get("results", []):
            cwe_id = issue.get("issue_cwe", {}).get("id")
            findings.append(SecurityFinding(
                type=issue.get("test_id", "Bandit"),
                severity=normalize_severity(issue.get("issue_severity")),
                file=filename,
                line=issue.get("line_number"),
                description=issue.get("issue_text", ""),
                evidence=issue.get("code"),
                owasp=get_owasp_mapping(cwe_id),
                cwe=f"CWE-{cwe_id}" if cwe_id else None,
                recommendation="Review the flagged code and apply a secure alternative."
            ))

    except subprocess.TimeoutExpired:
        findings.append(SecurityFinding(
            type="ScannerTimeout", severity="HIGH", file=filename,
            description="Bandit scan exceeded the allowed execution time."
        ))
    except json.JSONDecodeError:
        findings.append(SecurityFinding(
            type="ScannerError", severity="HIGH", file=filename,
            description="Bandit returned an invalid JSON response."
        ))
    except FileNotFoundError:
        findings.append(SecurityFinding(
            type="ScannerUnavailable", severity="HIGH", file=filename,
            description="Bandit executable was not found.",
            recommendation="Install Bandit and make sure it is available in PATH."
        ))
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass

    return findings


def run_semgrep(code: str, filename: str) -> List[SecurityFinding]:
    findings = []
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        temp_path = f.name

    try:
        result = subprocess.run(
            ["semgrep", "--config", "p/python", "--json", "--quiet", temp_path],
            capture_output=True, text=True, timeout=60
        )

        if not result.stdout.strip():
            if result.returncode != 0:
                findings.append(SecurityFinding(
                    type="ScannerError", severity="HIGH", file=filename,
                    description=f"Semgrep scan failed: {result.stderr.strip()}",
                    recommendation="Check the Semgrep installation and scanner configuration."
                ))
            return findings

        for item in json.loads(result.stdout).get("results", []):
            extra = item.get("extra", {})
            metadata = extra.get("metadata", {})
            cwe = extract_cwe(metadata.get("cwe"))
            owasp = metadata.get("owasp")

            if isinstance(owasp, list):
                owasp = owasp[0] if owasp else None

            if not owasp:
                owasp = get_owasp_mapping(get_cwe_id(cwe))

            findings.append(SecurityFinding(
                type=item.get("check_id", "Semgrep"),
                severity=normalize_severity(extra.get("severity")),
                file=filename,
                line=item.get("start", {}).get("line"),
                description=extra.get("message", "Security issue detected by Semgrep."),
                evidence=extra.get("lines"),
                owasp=owasp,
                cwe=cwe,
                recommendation="Review the Semgrep finding and apply the recommended secure coding practice."
            ))

    except subprocess.TimeoutExpired:
        findings.append(SecurityFinding(
            type="SemgrepTimeout", severity="HIGH", file=filename,
            description="Semgrep scan exceeded the allowed execution time."
        ))
    except json.JSONDecodeError:
        findings.append(SecurityFinding(
            type="SemgrepError", severity="HIGH", file=filename,
            description="Semgrep returned an invalid JSON response."
        ))
    except FileNotFoundError:
        findings.append(SecurityFinding(
            type="SemgrepUnavailable", severity="HIGH", file=filename,
            description="Semgrep executable was not found.",
            recommendation="Install Semgrep and make sure it is available in PATH."
        ))
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass

    return findings


def run_gitleaks(code: str, filename: str) -> List[SecurityFinding]:
    findings = []
    safe_filename = get_safe_filename(filename)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = os.path.join(temp_dir, safe_filename)
        report_path = os.path.join(temp_dir, "gitleaks-report.json")

        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(code)

        try:
            result = subprocess.run(
                [
                    GITLEAKS_PATH, "detect", "--source", temp_dir, "--no-git",
                    "--report-format", "json", "--report-path", report_path,
                    "--exit-code", "0"
                ],
                capture_output=True, text=True, timeout=60
            )

            if not os.path.exists(report_path):
                if result.returncode != 0:
                    findings.append(SecurityFinding(
                        type="GitleaksError", severity="HIGH", file=filename,
                        description="Gitleaks scan failed.",
                        recommendation="Check the Gitleaks installation and configuration."
                    ))
                return findings

            for secret in json.load(open(report_path, encoding="utf-8")):
                findings.append(SecurityFinding(
                    type="Gitleaks",
                    severity="HIGH",
                    file=filename,
                    line=secret.get("StartLine"),
                    description=f"Potential hardcoded secret detected: {secret.get('Description', 'Secret')}",
                    evidence="[REDACTED]",
                    owasp="A07:2021 - Identification and Authentication Failures",
                    recommendation="Remove the hardcoded secret and store credentials securely using environment variables or a secret management system."
                ))

        except subprocess.TimeoutExpired:
            findings.append(SecurityFinding(
                type="GitleaksTimeout", severity="HIGH", file=filename,
                description="Gitleaks scan exceeded the allowed execution time."
            ))
        except FileNotFoundError:
            findings.append(SecurityFinding(
                type="GitleaksUnavailable", severity="HIGH", file=filename,
                description="Gitleaks executable was not found.",
                recommendation="Install Gitleaks and make sure it is available in PATH or set GITLEAKS_PATH."
            ))
        except json.JSONDecodeError:
            findings.append(SecurityFinding(
                type="GitleaksError", severity="HIGH", file=filename,
                description="Gitleaks returned an invalid JSON report."
            ))

    return findings


@app.post("/scan", response_model=SecurityResponse)
def scan_code(request: CodeRequest):
    filename = get_safe_filename(request.filename)
    findings = (
        run_bandit(request.code, filename)
        + run_semgrep(request.code, filename)
        + run_gitleaks(request.code, filename)
    )

    findings = deduplicate_findings(findings)

    return SecurityResponse(
        status="completed",
        filename=filename,
        total_findings=len(findings),
        findings=findings
    )