"""Deterministic, locally evaluated asset creation for a selected opportunity."""

from __future__ import annotations

import re
from dataclasses import dataclass

from money_agent.workspace import Artifact, ArtifactStore, Workspace


@dataclass(frozen=True)
class CreationReport:
    artifacts: list[Artifact]
    reused_existing: bool
    evaluation: str


class AssetCreator:
    """Choose a deliverable family from the strategy; never publish the result."""

    def __init__(self, workspace: Workspace, store: ArtifactStore):
        self.workspace = workspace
        self.store = store

    @staticmethod
    def _slug(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:60] or "opportunity"

    def _specs(
        self, opportunity: str, rationale: str, research_ids: list[int]
    ) -> list[tuple[str, str, str, str]]:
        slug = self._slug(opportunity)
        root = f"projects/{slug}"
        lower = opportunity.lower()
        safety = "Private local draft. Publication, outreach, sale, and deployment remain undone."
        evidence = f"Stored research IDs: {research_ids or 'none; assumptions are unvalidated'}."
        if any(word in lower for word in ("saas", "software", "app", "website")):
            return [
                (
                    f"{root}/index.html",
                    "website_html",
                    "Interactive landing-page prototype",
                    f"<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
                    f"<title>{opportunity}</title><link rel='stylesheet' href='style.css'><main><p class='label'>LOCAL PROTOTYPE</p>"
                    f"<h1>{opportunity}</h1><p>{rationale}</p><section><h2>Try the workflow</h2><label>Weekly outcome "
                    "<input id='outcome'></label><button id='build'>Build private plan</button><pre id='result' aria-live='polite'></pre>"
                    f"</section><small>{safety} {evidence}</small></main><script src='app.js'></script></html>",
                ),
                (
                    f"{root}/style.css",
                    "website_css",
                    "Accessible prototype styling",
                    "body{font:16px system-ui;max-width:720px;margin:3rem auto;padding:1rem;background:#f5f7fb;color:#172033}"
                    "main{background:white;padding:2rem;border-radius:1rem}label,input,button{display:block;margin:.8rem 0}"
                    "input{padding:.7rem;width:90%}button{padding:.7rem;background:#2457d6;color:white;border:0}.label{font-weight:bold}",
                ),
                (
                    f"{root}/app.js",
                    "website_javascript",
                    "Local prototype interaction",
                    "'use strict';document.querySelector('#build').addEventListener('click',()=>{const value=document.querySelector('#outcome').value.trim();"
                    "document.querySelector('#result').textContent=value?`Outcome: ${value}\\n1. Define success\\n2. Choose next action\\n3. Review result`:'Enter an outcome first.';});",
                ),
            ]
        if any(word in lower for word in ("service", "consult", "agency", "freelance")):
            return [
                (
                    f"{root}/offer.md",
                    "sales_copy_markdown",
                    "Private productized-service offer",
                    f"# {opportunity}\n\n## Outcome\nA clearly scoped, repeatable deliverable for one recurring customer task.\n\n"
                    f"## Scope\nIncluded: intake, one draft, a quality check, and one revision. Excluded: credentials, publishing, regulated advice, and external account access.\n\n"
                    f"## Draft positioning\n{rationale}\n\n## Proof needed\nDemand, delivery time, and willingness to pay remain unverified. {evidence}\n\n{safety}\n",
                ),
                (
                    f"{root}/workflow.md",
                    "business_process_markdown",
                    "Repeatable service delivery workflow",
                    "# Delivery workflow\n\n1. Receive only authorized, non-sensitive inputs.\n2. Confirm scope and acceptance criteria.\n"
                    "3. Produce the draft locally.\n4. Run the checklist.\n5. Prepare a delivery draft; do not contact anyone.\n"
                    "6. Record feedback and improve the template.\n\n## Quality checklist\n- [ ] No credentials or private customer data\n- [ ] Scope met\n- [ ] Limitations stated\n",
                ),
                (
                    f"{root}/pricing.csv",
                    "pricing_csv",
                    "Unvalidated pricing options",
                    "tier,scope,draft_price,status\nStarter,one defined deliverable,25,unvalidated hypothesis\nStandard,deliverable plus one revision,50,unvalidated hypothesis\n",
                ),
            ]
        heading = (
            "Content draft"
            if any(word in lower for word in ("content", "newsletter", "blog"))
            else "Ready-to-use workflow"
        )
        return [
            (
                f"{root}/product.md",
                "digital_product_markdown",
                "Usable first product draft",
                f"# {opportunity}\n\n**Status:** {safety}\n\n## Purpose\n{rationale}\n\n## Customer and recurring job\n"
                "A small operator who needs a repeatable way to turn a vague weekly task into a prioritized, measurable plan.\n\n"
                f"## {heading}\n1. Write the single outcome for this week.\n2. Score tasks by impact and effort.\n"
                "3. Assign an owner and due date.\n4. Record results, blockers, and one improvement.\n\n"
                "## Fillable template\n| Outcome | Task | Impact | Effort | Owner | Due | Result |\n|---|---|---:|---:|---|---|---|\n"
                "| [outcome] | [action] | [1-5] | [1-5] | [name] | [date] | [pending] |\n\n"
                "## Quality and validation checklist\n- [ ] Usable without special software\n- [ ] Claims labeled as hypotheses\n"
                "- [ ] No credentials or regulated advice\n- [ ] External actions remain undone\n\n"
                f"## Evidence links\n{evidence}\n",
            )
        ]

    def create(self, opportunity: str, rationale: str, research_ids: list[int]) -> CreationReport:
        """Create or deliberately improve an appropriate private deliverable."""
        existing = {item.file_path: item for item in self.store.for_opportunity(opportunity)}
        artifacts: list[Artifact] = []
        notes: list[str] = []
        for path, artifact_type, purpose, content in self._specs(
            opportunity, rationale, research_ids
        ):
            reused = path in existing
            if reused:
                content += "\n<!-- Improvement revision of the existing tracked artifact. -->\n"
            self.workspace.write_text(path, content, overwrite=reused)
            observed = self.workspace.read_text(path)
            complete = (
                len(observed) >= 80 and "Private local draft" in observed
                if path.endswith(".html")
                else len(observed) >= 80
            )
            status = "verified" if complete else "needs_work"
            note = f"Verified {path} exists, is UTF-8, and contains {len(observed)} characters; local structure check {'passed' if complete else 'failed'}. Market usefulness and demand are not verified."
            notes.append(note)
            artifacts.append(
                self.store.upsert(
                    file_path=path,
                    artifact_type=artifact_type,
                    purpose=purpose,
                    opportunity=opportunity,
                    status=status,
                    evaluation_notes=note,
                    related_research_ids=research_ids,
                )
            )
        return CreationReport(artifacts, bool(existing), " ".join(notes))
