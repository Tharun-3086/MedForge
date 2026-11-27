"""Versioned source-preserving medical extraction contract; no clinical calculations."""
from typing import Literal
import re
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.services.health_readings import LABELS

MEDICAL_SCHEMA_VERSION = "diabetes-measurements-v1"
# Providers may ignore enum output and return an explicit laboratory label.
# Canonicalize names only, never a numeric value or unit.
PARAMETER_ALIASES = {
    'glucose':'blood_glucose','bloodsugar':'blood_glucose','plasmaglucose':'blood_glucose',
    'fastingplasmaglucose':'fasting_glucose','fastingbloodglucose':'fasting_glucose','fastingbloodsugar':'fasting_glucose','fastingglucose':'fasting_glucose','fbs':'fasting_glucose','fbg':'fasting_glucose',
    'postprandialplasmaglucose':'postmeal_glucose','postprandialbloodglucose':'postmeal_glucose','postprandialbloodsugar':'postmeal_glucose','postmealbloodglucose':'postmeal_glucose','ppbs':'postmeal_glucose',
    'randombloodglucose':'random_glucose','randomplasmaglucose':'random_glucose','randombloodsugar':'random_glucose','rbs':'random_glucose',
    'serumcreatinine':'creatinine','screatinine':'creatinine','estimatedglomerularfiltrationrate':'egfr',
    'urinealbumintocreatinineratio':'uacr','urinealbumincreatinineratio':'uacr',
    'glycatedhaemoglobin':'hba1c','glycatedhemoglobin':'hba1c',
    **{re.sub(r'[^a-z0-9]','',key):key for key in LABELS},
    **{re.sub(r'[^a-z0-9]','',label.lower()):key for key,label in LABELS.items()}
}

class MedicalMeasurement(BaseModel):
    model_config = ConfigDict(extra="ignore")
    parameter: str = Field(min_length=1,max_length=100)
    raw_parameter: str = Field(default="",exclude=True,max_length=100)

    @model_validator(mode='before')
    @classmethod
    def canonical_parameter(cls,data):
        if not isinstance(data,dict):return data
        raw=str(data.get('parameter',''))
        key=re.sub(r'[^a-z0-9]','',raw.lower())
        parameter=PARAMETER_ALIASES.get(key,raw)
        # A generic glucose label may be refined only by an explicit source label.
        quote=str(data.get('quote',''))
        if parameter=='blood_glucose':
            contexts=[]
            for pattern,name in [(r'\bfasting\s+(?:(?:plasma|blood)\s+)?(?:glucose|sugar)\b','fasting_glucose'),
                                 (r'\bpost[ -]?(?:meal|prandial)\s+(?:(?:plasma|blood)\s+)?(?:glucose|sugar)\b','postmeal_glucose'),
                                 (r'\brandom\s+(?:(?:plasma|blood)\s+)?(?:glucose|sugar)\b','random_glucose')]:
                if re.search(pattern,quote,re.I):contexts.append(name)
            if len(contexts)==1:parameter=contexts[0]
        return dict(data,parameter=parameter,raw_parameter=raw)

    value: str = Field(min_length=1,max_length=80)
    unit: str = Field(max_length=50)
    reference_range: str = Field(default="",max_length=200)
    test_date: str = Field(default="",max_length=40)
    quote: str = Field(min_length=1,max_length=1000)
    block_ids: list[str] = Field(default_factory=list,max_length=20)
    confidence: float | None = Field(default=None,ge=0,le=1)

# Explicit schema avoids provider-specific $ref handling. Every property is
# required for OpenAI strict output; empty strings mean absent in the source.
MEASUREMENT_JSON_SCHEMA = {
    "type":"object", "additionalProperties":False,
    "properties": {
        "parameter":{"type":"string","enum":list(LABELS),"description":"Return the exact internal enum code, not the test label. Never confuse a result with a reference limit or medication dose."},
        "value":{"type":"string","description":"Exact result number (or BP pair), excluding unit. Preserve comparators; never calculate or guess."},
        "unit":{"type":"string","description":"Exact unit written beside this result. Empty if missing; never infer or repair."},
        "reference_range":{"type":"string","description":"Exact laboratory reference range for this result, or empty. This is not a personalized treatment target."},
        "test_date":{"type":"string","description":"Exact date text for this sample/test, or empty. Do not use upload date."},
        "quote":{"type":"string","description":"Exact source row/text containing the parameter, result and unit. Do not rewrite OCR. Preserve uncertainty."},
        "block_ids":{"type":"array","items":{"type":"string"},"description":"IDs of supplied text blocks; empty for image-only evidence."},
        "confidence":{"type":["number","null"],"description":"Model confidence, not a medical accuracy probability."}
    },
    "required":["parameter","value","unit","reference_range","test_date","quote","block_ids","confidence"]
}
