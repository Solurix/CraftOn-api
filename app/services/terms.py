"""Human-readable contract terms (Phase 1 placeholder wording).

On confirm we record the contract type and generate a localized, human-readable
terms document. **The wording is placeholder text pending legal review**
(社労士 / 税理士 / 弁護士) — see docs/08. We generate it on demand from i18n keys
rather than storing it, so it stays in sync with the catalog.
"""

from __future__ import annotations

from app.core.i18n import translate
from app.models.enums import ContractType, WorkerClass

# worker_class → contract type (docs/08 §"Contract / tax routing").
CONTRACT_TYPE_BY_CLASS: dict[WorkerClass, ContractType] = {
    WorkerClass.EMPLOYEE: ContractType.EMPLOYMENT_DAYLABOR,
    WorkerClass.FREELANCE: ContractType.SUBCONTRACT,
}


def contract_type_for(worker_class: WorkerClass) -> ContractType:
    return CONTRACT_TYPE_BY_CLASS[worker_class]


def generate_terms(
    *,
    contract_type: ContractType,
    worker_name: str,
    company_name: str,
    work_date: str,
    daily_wage: int,
    locale: str,
) -> str:
    """Render the placeholder terms document for a matching."""
    title = translate(f"terms.title.{contract_type.value}", locale)
    body = translate(
        f"terms.body.{contract_type.value}",
        locale,
        worker=worker_name,
        company=company_name,
        date=work_date,
        wage=daily_wage,
    )
    disclaimer = translate("terms.disclaimer", locale)
    return f"{title}\n\n{body}\n\n{disclaimer}"
