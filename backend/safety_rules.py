"""
Clinical Drug Safety Engine — Deterministic Safety Rules

Pure rule-based safety checks that NEVER depend on LLM output.
These run on EVERY request regardless of whether LLM succeeds or fails.

Includes:
- Drug-class allergy matching
- Drug-condition contraindication rules
- Fallback interaction lookup
- Known drug dictionary for fuzzy matching
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from models import (
    AllergyAlert,
    Contraindication,
    DrugInteraction,
    Severity,
    ConfidenceLevel,
)


# ---------------------------------------------------------------------------
# Drug-Class Mappings (for allergy cross-matching)
# ---------------------------------------------------------------------------

DRUG_CLASS_MAP: dict[str, list[str]] = {
    "penicillins": [
        "penicillin", "amoxicillin", "ampicillin", "piperacillin",
        "nafcillin", "oxacillin", "dicloxacillin", "amoxicillin-clavulanate",
        "ampicillin-sulbactam", "piperacillin-tazobactam", "ticarcillin",
    ],
    "cephalosporins": [
        "cephalexin", "cefazolin", "ceftriaxone", "cefepime", "cefuroxime",
        "cefdinir", "cefixime", "cefpodoxime", "ceftazidime", "cefotaxime",
    ],
    "sulfonamides": [
        "sulfamethoxazole", "sulfasalazine", "sulfadiazine",
        "trimethoprim-sulfamethoxazole", "sulfacetamide",
    ],
    "nsaids": [
        "ibuprofen", "naproxen", "diclofenac", "indomethacin", "piroxicam",
        "meloxicam", "celecoxib", "ketorolac", "flurbiprofen", "etodolac",
        "mefenamic acid", "ketoprofen",
    ],
    "statins": [
        "atorvastatin", "simvastatin", "rosuvastatin", "pravastatin",
        "lovastatin", "fluvastatin", "pitavastatin",
    ],
    "ace_inhibitors": [
        "lisinopril", "enalapril", "ramipril", "captopril", "benazepril",
        "fosinopril", "quinapril", "perindopril", "trandolapril", "moexipril",
    ],
    "arbs": [
        "losartan", "valsartan", "irbesartan", "candesartan", "olmesartan",
        "telmisartan", "azilsartan",
    ],
    "beta_blockers": [
        "metoprolol", "atenolol", "propranolol", "carvedilol", "bisoprolol",
        "nadolol", "labetalol", "nebivolol", "sotalol", "timolol",
    ],
    "fluoroquinolones": [
        "ciprofloxacin", "levofloxacin", "moxifloxacin", "ofloxacin",
        "norfloxacin", "gemifloxacin",
    ],
    "opioids": [
        "morphine", "codeine", "tramadol", "oxycodone", "hydrocodone",
        "fentanyl", "methadone", "hydromorphone", "meperidine", "tapentadol",
        "buprenorphine",
    ],
    "macrolides": [
        "azithromycin", "clarithromycin", "erythromycin",
    ],
    "tetracyclines": [
        "doxycycline", "tetracycline", "minocycline", "tigecycline",
    ],
    "benzodiazepines": [
        "diazepam", "lorazepam", "alprazolam", "clonazepam", "midazolam",
        "temazepam", "triazolam", "oxazepam", "chlordiazepoxide",
    ],
    "ssris": [
        "fluoxetine", "sertraline", "paroxetine", "citalopram",
        "escitalopram", "fluvoxamine",
    ],
    "maois": [
        "phenelzine", "tranylcypromine", "selegiline", "isocarboxazid",
        "moclobemide",
    ],
    "aminoglycosides": [
        "gentamicin", "tobramycin", "amikacin", "streptomycin", "neomycin",
    ],
    "anticoagulants": [
        "warfarin", "heparin", "enoxaparin", "rivaroxaban", "apixaban",
        "dabigatran", "edoxaban", "fondaparinux",
    ],
    "antiplatelets": [
        "aspirin", "clopidogrel", "ticagrelor", "prasugrel", "dipyridamole",
    ],
    "thiazides": [
        "hydrochlorothiazide", "chlorthalidone", "indapamide", "metolazone",
    ],
    "loop_diuretics": [
        "furosemide", "bumetanide", "torsemide", "ethacrynic acid",
    ],
    "calcium_channel_blockers": [
        "amlodipine", "nifedipine", "verapamil", "diltiazem", "felodipine",
        "nicardipine", "nimodipine",
    ],
    "corticosteroids": [
        "prednisone", "prednisolone", "methylprednisolone", "dexamethasone",
        "hydrocortisone", "budesonide", "beclomethasone", "triamcinolone",
    ],
}

# Build reverse lookup: drug_name -> list of classes
DRUG_TO_CLASSES: dict[str, list[str]] = {}
for class_name, drugs in DRUG_CLASS_MAP.items():
    for drug in drugs:
        DRUG_TO_CLASSES.setdefault(drug, []).append(class_name)

# Cross-reactivity rules: allergy to class_a may cross-react with class_b
CROSS_REACTIVITY: dict[str, list[tuple[str, str]]] = {
    "penicillins": [("cephalosporins", "Penicillin-cephalosporin cross-reactivity (~2-5% risk)")],
    "cephalosporins": [("penicillins", "Cephalosporin-penicillin cross-reactivity (~1-2% risk)")],
    "sulfonamides": [("thiazides", "Sulfonamide-thiazide structural similarity (~rare cross-reactivity)")],
}


# ---------------------------------------------------------------------------
# Contraindication Rules (condition -> list of contraindicated drugs/classes)
# ---------------------------------------------------------------------------

CONTRAINDICATION_RULES: dict[str, list[dict]] = {
    "kidney disease": [
        {"drugs": ["nsaids"], "type": "class", "reason": "NSAIDs reduce renal blood flow via prostaglandin inhibition, worsening kidney function", "severity": "high"},
        {"drugs": ["aspirin"], "type": "drug", "reason": "Aspirin has NSAID properties — inhibits renal prostaglandins, reducing renal blood flow. Use with caution; low antiplatelet doses (75-100mg) may be acceptable with monitoring", "severity": "medium"},
        {"drugs": ["metformin"], "type": "drug", "reason": "Risk of lactic acidosis due to impaired metformin clearance in renal impairment", "severity": "high"},
        {"drugs": ["lithium"], "type": "drug", "reason": "Lithium has narrow therapeutic index and is renally cleared; impaired clearance risks toxicity", "severity": "high"},
        {"drugs": ["aminoglycosides"], "type": "class", "reason": "Aminoglycosides are nephrotoxic and renally cleared; risk of accumulation and further renal damage", "severity": "high"},
        {"drugs": ["vancomycin"], "type": "drug", "reason": "Vancomycin is nephrotoxic; requires careful dose adjustment based on renal function", "severity": "medium"},
    ],
    "renal impairment": [
        {"drugs": ["nsaids"], "type": "class", "reason": "NSAIDs reduce renal blood flow, worsening renal impairment", "severity": "high"},
        {"drugs": ["metformin"], "type": "drug", "reason": "Lactic acidosis risk with impaired metformin renal clearance", "severity": "high"},
        {"drugs": ["lithium"], "type": "drug", "reason": "Impaired renal clearance increases lithium toxicity risk", "severity": "high"},
    ],
    "liver disease": [
        {"drugs": ["acetaminophen", "paracetamol"], "type": "drug", "reason": "Hepatotoxic metabolite (NAPQI) accumulates in liver disease; maximum dose should be reduced to 2g/day", "severity": "high"},
        {"drugs": ["statins"], "type": "class", "reason": "Statins undergo hepatic metabolism; liver disease increases risk of hepatotoxicity and rhabdomyolysis", "severity": "high"},
        {"drugs": ["methotrexate"], "type": "drug", "reason": "Methotrexate is hepatotoxic; existing liver disease significantly increases risk of fibrosis and cirrhosis", "severity": "high"},
        {"drugs": ["valproic acid", "valproate"], "type": "drug", "reason": "Valproic acid is hepatotoxic; can cause fatal hepatic failure in liver disease", "severity": "high"},
    ],
    "hepatic impairment": [
        {"drugs": ["statins"], "type": "class", "reason": "Increased hepatotoxicity risk in hepatic impairment", "severity": "high"},
        {"drugs": ["methotrexate"], "type": "drug", "reason": "Hepatotoxicity risk significantly elevated in hepatic impairment", "severity": "high"},
    ],
    "pregnancy": [
        {"drugs": ["warfarin"], "type": "drug", "reason": "Warfarin crosses the placenta causing fetal warfarin syndrome (nasal hypoplasia, stippled epiphyses, CNS abnormalities)", "severity": "high"},
        {"drugs": ["methotrexate"], "type": "drug", "reason": "Methotrexate is a known teratogen and abortifacient; absolutely contraindicated in pregnancy", "severity": "high"},
        {"drugs": ["ace_inhibitors", "arbs"], "type": "class", "reason": "ACE inhibitors and ARBs cause fetal renal dysgenesis, oligohydramnios, and skull defects in 2nd/3rd trimester", "severity": "high"},
        {"drugs": ["statins"], "type": "class", "reason": "Statins are FDA Category X; cholesterol is essential for fetal development", "severity": "high"},
        {"drugs": ["isotretinoin"], "type": "drug", "reason": "Isotretinoin is a potent teratogen causing craniofacial, cardiac, and CNS malformations", "severity": "high"},
        {"drugs": ["valproic acid", "valproate"], "type": "drug", "reason": "Valproic acid causes neural tube defects and neurodevelopmental impairment", "severity": "high"},
    ],
    "asthma": [
        {"drugs": ["propranolol", "nadolol", "timolol", "sotalol"], "type": "drug", "reason": "Non-selective beta-blockers block beta-2 receptors in bronchial smooth muscle, causing bronchospasm", "severity": "high"},
        {"drugs": ["aspirin"], "type": "drug", "reason": "Aspirin can trigger bronchospasm in aspirin-sensitive asthma (Samter's triad)", "severity": "medium"},
    ],
    "heart failure": [
        {"drugs": ["nsaids"], "type": "class", "reason": "NSAIDs cause sodium and water retention, worsening heart failure and increasing hospitalization risk", "severity": "high"},
        {"drugs": ["verapamil", "diltiazem"], "type": "drug", "reason": "Non-dihydropyridine calcium channel blockers have negative inotropic effects, worsening heart failure", "severity": "high"},
        {"drugs": ["thiazolidinediones", "pioglitazone", "rosiglitazone"], "type": "drug", "reason": "Thiazolidinediones cause fluid retention, exacerbating heart failure", "severity": "high"},
    ],
    "peptic ulcer": [
        {"drugs": ["nsaids"], "type": "class", "reason": "NSAIDs inhibit protective prostaglandin synthesis in gastric mucosa, worsening ulceration and risk of GI bleeding", "severity": "high"},
        {"drugs": ["aspirin"], "type": "drug", "reason": "Aspirin damages gastric mucosa directly and inhibits protective prostaglandins, increasing ulcer and bleeding risk", "severity": "high"},
        {"drugs": ["corticosteroids"], "type": "class", "reason": "Corticosteroids impair mucosal healing and increase risk of GI perforation, especially with concurrent NSAID use", "severity": "medium"},
    ],
    "diabetes": [
        {"drugs": ["corticosteroids"], "type": "class", "reason": "Corticosteroids cause hyperglycemia through increased hepatic gluconeogenesis and insulin resistance", "severity": "medium"},
        {"drugs": ["thiazides"], "type": "class", "reason": "Thiazides impair glucose tolerance and may worsen glycemic control through hypokalemia-mediated insulin resistance", "severity": "medium"},
        {"drugs": ["beta_blockers"], "type": "class", "reason": "Beta-blockers may mask hypoglycemia symptoms and impair glycogenolysis", "severity": "low"},
    ],
    "epilepsy": [
        {"drugs": ["tramadol"], "type": "drug", "reason": "Tramadol lowers seizure threshold; increased seizure risk in epilepsy patients", "severity": "high"},
        {"drugs": ["bupropion"], "type": "drug", "reason": "Bupropion dose-dependently lowers seizure threshold; contraindicated in seizure disorders", "severity": "high"},
        {"drugs": ["meperidine"], "type": "drug", "reason": "Meperidine's metabolite normeperidine is neurotoxic and lowers seizure threshold", "severity": "high"},
    ],
    "bleeding disorders": [
        {"drugs": ["anticoagulants"], "type": "class", "reason": "Anticoagulants increase bleeding risk significantly in patients with underlying bleeding disorders", "severity": "high"},
        {"drugs": ["antiplatelets"], "type": "class", "reason": "Antiplatelets impair hemostasis further in patients with bleeding disorders", "severity": "high"},
        {"drugs": ["nsaids"], "type": "class", "reason": "NSAIDs inhibit platelet function and may cause GI bleeding, dangerous in bleeding disorders", "severity": "high"},
    ],
    "hypertension": [
        {"drugs": ["nsaids"], "type": "class", "reason": "NSAIDs cause sodium retention and may attenuate the effect of antihypertensive medications", "severity": "medium"},
        {"drugs": ["corticosteroids"], "type": "class", "reason": "Corticosteroids cause sodium and water retention, elevating blood pressure", "severity": "medium"},
    ],
    "gout": [
        {"drugs": ["thiazides"], "type": "class", "reason": "Thiazides reduce uric acid excretion, potentially precipitating gout attacks", "severity": "medium"},
        {"drugs": ["aspirin"], "type": "drug", "reason": "Low-dose aspirin impairs uric acid excretion, worsening hyperuricemia", "severity": "medium"},
    ],
    "myasthenia gravis": [
        {"drugs": ["aminoglycosides"], "type": "class", "reason": "Aminoglycosides have neuromuscular blocking properties, worsening myasthenic weakness", "severity": "high"},
        {"drugs": ["fluoroquinolones"], "type": "class", "reason": "Fluoroquinolones can exacerbate muscle weakness in myasthenia gravis", "severity": "high"},
    ],
}

# Condition aliases (normalize common variations)
CONDITION_ALIASES: dict[str, str] = {
    "ckd": "kidney disease",
    "chronic kidney disease": "kidney disease",
    "renal failure": "kidney disease",
    "kidney failure": "kidney disease",
    "renal insufficiency": "renal impairment",
    "hepatic disease": "liver disease",
    "liver failure": "liver disease",
    "cirrhosis": "liver disease",
    "hepatitis": "liver disease",
    "pregnant": "pregnancy",
    "expecting": "pregnancy",
    "copd": "asthma",  # Similar bronchospasm concern
    "chf": "heart failure",
    "congestive heart failure": "heart failure",
    "gastric ulcer": "peptic ulcer",
    "stomach ulcer": "peptic ulcer",
    "gi ulcer": "peptic ulcer",
    "duodenal ulcer": "peptic ulcer",
    "type 1 diabetes": "diabetes",
    "type 2 diabetes": "diabetes",
    "diabetes mellitus": "diabetes",
    "seizure disorder": "epilepsy",
    "seizures": "epilepsy",
    "convulsions": "epilepsy",
    "coagulopathy": "bleeding disorders",
    "hemophilia": "bleeding disorders",
    "high blood pressure": "hypertension",
    "htn": "hypertension",
}


# ---------------------------------------------------------------------------
# Known Drug Dictionary (for fuzzy matching)
# ---------------------------------------------------------------------------

def _build_known_drugs() -> set[str]:
    """Build a comprehensive set of all known drug names from our data."""
    drugs: set[str] = set()
    for class_drugs in DRUG_CLASS_MAP.values():
        drugs.update(class_drugs)
    # Add specific drugs mentioned in contraindication rules
    for rules in CONTRAINDICATION_RULES.values():
        for rule in rules:
            if rule["type"] == "drug":
                drugs.update(d.lower() for d in rule["drugs"])
    # Add common drugs not in classes
    additional_drugs = {
        "acetaminophen", "paracetamol", "metformin", "lithium", "vancomycin",
        "methotrexate", "isotretinoin", "bupropion", "meperidine",
        "pioglitazone", "rosiglitazone", "valproic acid", "valproate",
        "phenytoin", "carbamazepine", "lamotrigine", "gabapentin",
        "pregabalin", "topiramate", "levetiracetam", "theophylline",
        "aminophylline", "digoxin", "amiodarone", "omeprazole",
        "pantoprazole", "lansoprazole", "esomeprazole", "rabeprazole",
        "ranitidine", "famotidine", "cimetidine", "sucralfate",
        "metoclopramide", "ondansetron", "domperidone",
        "insulin", "glipizide", "glyburide", "glimepiride", "sitagliptin",
        "empagliflozin", "dapagliflozin", "canagliflozin", "liraglutide",
        "semaglutide", "levothyroxine", "potassium", "iron",
        "calcium", "magnesium", "zinc", "antacids", "contrast dye",
        "alcohol", "spironolactone", "eplerenone", "amiloride",
        "allopurinol", "febuxostat", "colchicine",
        "sildenafil", "tadalafil", "nitrates", "nitroglycerin",
        "isosorbide mononitrate", "isosorbide dinitrate",
        "cyclosporine", "tacrolimus", "mycophenolate", "azathioprine",
    }
    drugs.update(additional_drugs)
    return drugs


KNOWN_DRUGS: set[str] = _build_known_drugs()


# ---------------------------------------------------------------------------
# Fallback Interaction Database
# ---------------------------------------------------------------------------

class FallbackDatabase:
    """
    Loads and indexes the fallback drug interaction database
    for O(1) pair-based lookup.
    """

    def __init__(self) -> None:
        self._interactions: dict[tuple[str, str], dict] = {}
        self._load()

    def _load(self) -> None:
        """Load fallback_interactions.json into a pair-indexed dictionary."""
        data_path = Path(os.path.dirname(os.path.abspath(__file__))) / "data" / "fallback_interactions.json"
        try:
            with open(data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for entry in data.get("interactions", []):
                drug_a = entry["drug_a"].lower().strip()
                drug_b = entry["drug_b"].lower().strip()
                # Index both orderings for O(1) lookup
                key_ab = (drug_a, drug_b)
                key_ba = (drug_b, drug_a)
                self._interactions[key_ab] = entry
                self._interactions[key_ba] = {
                    **entry,
                    "drug_a": entry["drug_b"],
                    "drug_b": entry["drug_a"],
                }
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            # Log but don't crash — system can still work with empty fallback
            print(f"WARNING: Failed to load fallback interactions: {e}")

    def lookup_pair(self, drug_a: str, drug_b: str) -> Optional[dict]:
        """Look up interaction between two drugs. Returns None if not found."""
        key = (drug_a.lower().strip(), drug_b.lower().strip())
        return self._interactions.get(key)

    def lookup_all_pairs(self, drugs: list[str]) -> list[DrugInteraction]:
        """Find all known interactions among a list of drugs."""
        interactions: list[DrugInteraction] = []
        seen_pairs: set[tuple[str, str]] = set()

        for i, drug_a in enumerate(drugs):
            for drug_b in drugs[i + 1:]:
                key = tuple(sorted([drug_a.lower().strip(), drug_b.lower().strip()]))
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)

                result = self.lookup_pair(drug_a, drug_b)
                if result:
                    try:
                        severity = Severity(result["severity"])
                    except ValueError:
                        severity = Severity.MEDIUM
                    interactions.append(DrugInteraction(
                        drug_a=result["drug_a"],
                        drug_b=result["drug_b"],
                        severity=severity,
                        mechanism=result.get("mechanism", "Known drug interaction"),
                        clinical_recommendation=result.get(
                            "clinical_recommendation",
                            "Consult physician before co-prescribing"
                        ),
                        source_confidence=ConfidenceLevel.HIGH,
                    ))

        return interactions

    @property
    def interaction_count(self) -> int:
        """Number of unique interactions in the database."""
        return len(self._interactions) // 2  # Each stored twice


# ---------------------------------------------------------------------------
# Allergy Checking
# ---------------------------------------------------------------------------

def check_allergies(
    medicines: list[str],
    known_allergies: list[str],
) -> list[AllergyAlert]:
    """
    Check proposed medicines against patient's known allergies.

    Performs three levels of matching:
    1. Exact match: medicine name == allergy name → critical
    2. Class match: medicine is in the same drug class as the allergy → high
    3. Cross-reactivity: medicine's class cross-reacts with allergy's class → medium
    """
    if not known_allergies:
        return []

    alerts: list[AllergyAlert] = []
    seen: set[tuple[str, str]] = set()  # (medicine, allergen) pairs to avoid duplicates
    normalized_allergies = [a.lower().strip() for a in known_allergies]

    for med in medicines:
        med_lower = med.lower().strip()

        for allergy in normalized_allergies:
            # 1. Exact match
            if med_lower == allergy:
                pair = (med_lower, allergy)
                if pair not in seen:
                    seen.add(pair)
                    alerts.append(AllergyAlert(
                        medicine=med_lower,
                        allergen=allergy,
                        reason=f"Direct allergy match: patient is allergic to {allergy}",
                        severity=Severity.CRITICAL,
                    ))
                continue

            # 2. Class match — is the medicine in the same class as the allergy?
            allergy_classes = set()
            # Check if allergy is a class name
            if allergy in DRUG_CLASS_MAP:
                allergy_classes.add(allergy)
            # Check if allergy is a drug name → get its classes
            if allergy in DRUG_TO_CLASSES:
                allergy_classes.update(DRUG_TO_CLASSES[allergy])

            med_classes = set()
            if med_lower in DRUG_TO_CLASSES:
                med_classes.update(DRUG_TO_CLASSES[med_lower])

            # Check for shared class
            shared_classes = allergy_classes & med_classes
            if shared_classes:
                pair = (med_lower, allergy)
                if pair not in seen:
                    seen.add(pair)
                    class_names = ", ".join(shared_classes)
                    alerts.append(AllergyAlert(
                        medicine=med_lower,
                        allergen=allergy,
                        reason=f"Drug-class allergy match: {med_lower} and {allergy} "
                               f"belong to the same class ({class_names})",
                        severity=Severity.HIGH,
                    ))
                continue

            # Check if medicine is IN the class that the allergy names
            if allergy in DRUG_CLASS_MAP and med_lower in DRUG_CLASS_MAP[allergy]:
                pair = (med_lower, allergy)
                if pair not in seen:
                    seen.add(pair)
                    alerts.append(AllergyAlert(
                        medicine=med_lower,
                        allergen=allergy,
                        reason=f"Drug-class allergy match: {med_lower} belongs to "
                               f"class '{allergy}' which patient is allergic to",
                        severity=Severity.HIGH,
                    ))
                continue

            # 3. Cross-reactivity check
            for allergy_class in allergy_classes:
                if allergy_class in CROSS_REACTIVITY:
                    for cross_class, reason in CROSS_REACTIVITY[allergy_class]:
                        if cross_class in med_classes or (
                            cross_class in DRUG_CLASS_MAP and
                            med_lower in DRUG_CLASS_MAP[cross_class]
                        ):
                            pair = (med_lower, allergy)
                            if pair not in seen:
                                seen.add(pair)
                                alerts.append(AllergyAlert(
                                    medicine=med_lower,
                                    allergen=allergy,
                                    reason=f"Cross-reactivity risk: {reason}",
                                    severity=Severity.MEDIUM,
                                ))

    return alerts


# ---------------------------------------------------------------------------
# Contraindication Checking
# ---------------------------------------------------------------------------

def check_contraindications(
    medicines: list[str],
    conditions: list[str],
    age: Optional[int] = None,
    weight: Optional[float] = None,
) -> tuple[list[Contraindication], list[str]]:
    """
    Check proposed medicines against patient conditions, age, and weight.

    Returns:
        tuple of (contraindications list, warnings list)
    """
    if not conditions and age is None and weight is None:
        return [], []

    contraindications: list[Contraindication] = []
    warnings: list[str] = []
    seen: set[tuple[str, str]] = set()  # (medicine, condition) to avoid duplicates

    normalized_conditions = []
    for cond in conditions:
        cond_lower = cond.lower().strip()
        # Apply aliases
        normalized = CONDITION_ALIASES.get(cond_lower, cond_lower)
        normalized_conditions.append(normalized)

    for condition in normalized_conditions:
        if condition not in CONTRAINDICATION_RULES:
            continue

        rules = CONTRAINDICATION_RULES[condition]
        for rule in rules:
            for med in medicines:
                med_lower = med.lower().strip()
                matched = False

                if rule["type"] == "class":
                    # Check if medicine belongs to any of the contraindicated classes
                    for class_name in rule["drugs"]:
                        if class_name in DRUG_CLASS_MAP and med_lower in DRUG_CLASS_MAP[class_name]:
                            matched = True
                            break
                        # Also check if the drug name matches the class name directly
                        if med_lower == class_name:
                            matched = True
                            break
                elif rule["type"] == "drug":
                    if med_lower in [d.lower() for d in rule["drugs"]]:
                        matched = True

                if matched:
                    pair = (med_lower, condition)
                    if pair not in seen:
                        seen.add(pair)
                        try:
                            severity = Severity(rule["severity"])
                        except ValueError:
                            severity = Severity.HIGH
                        contraindications.append(Contraindication(
                            medicine=med_lower,
                            condition=condition,
                            reason=rule["reason"],
                            severity=severity,
                        ))

    # Age-based warnings
    if age is not None:
        if age < 12:
            warnings.append(
                f"PEDIATRIC PATIENT (age {age}): Verify all doses are "
                f"appropriate for pediatric use. Some medications may require "
                f"weight-based dosing or are contraindicated in children."
            )
        elif age > 65:
            warnings.append(
                f"GERIATRIC PATIENT (age {age}): Consider reduced starting "
                f"doses. Increased sensitivity to CNS depressants, "
                f"anticholinergics, and renally-cleared medications. "
                f"Beers Criteria should be reviewed."
            )

    # Weight-based warnings
    if weight is not None:
        if weight < 40:
            warnings.append(
                f"LOW BODY WEIGHT ({weight}kg): Dose adjustments likely "
                f"required. Standard adult doses may result in toxicity. "
                f"Consider weight-based dosing for narrow therapeutic index drugs."
            )
        elif weight > 120:
            warnings.append(
                f"HIGH BODY WEIGHT ({weight}kg): Some medications may require "
                f"dose adjustment. Consider actual body weight vs. ideal body "
                f"weight for dosing calculations."
            )

    return contraindications, warnings


# ---------------------------------------------------------------------------
# Module-level instances
# ---------------------------------------------------------------------------

# Pre-load fallback database at import time for performance
fallback_db = FallbackDatabase()
