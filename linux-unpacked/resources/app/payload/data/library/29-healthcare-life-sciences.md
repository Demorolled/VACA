# 🏥 Healthcare & Life Sciences

> Reference for building healthcare applications — EHR/clinical systems, HL7 FHIR interoperability, medical imaging, HIPAA compliance, and health data standards.
> Extracted from The Programming Bible's Healthcare & Life Sciences level.

---

## 1. Healthcare System Landscape

```
┌─────────────────────────────────────────────────────┐
│              HEALTHCARE SYSTEM LANDSCAPE             │
│                                                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────┐│
│  │ EHR/EMR  │  │  LIS     │  │  RIS     │  │  PACS ││
│  │ Clinical │  │Laboratory│  │Radiology │  │Imaging││
│  │ Records  │  │   Data   │  │  System  │  │       ││
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └───┬───┘│
│       │             │             │             │     │
│       └─────────────┴─────────────┴─────────────┘     │
│                        │                              │
│                 ┌──────▼──────┐                       │
│                 │   Interop   │                       │
│                 │   (FHIR)    │                       │
│                 └─────────────┘                       │
└─────────────────────────────────────────────────────┘
```

| System | Function | Data |
|---|---|---|
| **EHR/EMR** (Electronic Health Records) | Patient records, clinical notes, orders | Demographics, diagnoses, medications, labs |
| **LIS** (Laboratory Information System) | Lab test tracking & results | Specimens, test results, panels |
| **RIS** (Radiology Information System) | Radiological workflow | Orders, scheduled exams, reports |
| **PACS** (Picture Archiving) | Medical image storage | DICOM images |
| **CDSS** (Clinical Decision Support) | Diagnostic & treatment recommendations | Clinical rules, alerts, guidelines |

---

## 2. EHR/Clinical Data Model

### Core Clinical Tables

```sql
-- Patient demographics
CREATE TABLE patients (
    patient_id      UUID PRIMARY KEY,
    mrn             VARCHAR(20) UNIQUE NOT NULL,  -- Medical Record Number
    first_name      VARCHAR(100) NOT NULL,
    last_name       VARCHAR(100) NOT NULL,
    dob             DATE NOT NULL,
    gender          VARCHAR(10),
    ssn_last4       VARCHAR(4),          -- Last 4 digits only for security
    address         JSONB,
    phone           VARCHAR(20),
    email           VARCHAR(255),
    preferred_language VARCHAR(10),
    race            VARCHAR(50),
    ethnicity       VARCHAR(50),
    deceased        BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Patient encounters (visits)
CREATE TABLE encounters (
    encounter_id    UUID PRIMARY KEY,
    patient_id      UUID NOT NULL REFERENCES patients(patient_id),
    encounter_type  VARCHAR(50) NOT NULL,   -- 'inpatient', 'outpatient', 'emergency', 'virtual'
    status          VARCHAR(20) NOT NULL,   -- 'planned', 'in-progress', 'completed', 'cancelled'
    start_time      TIMESTAMP NOT NULL,
    end_time        TIMESTAMP,
    department      VARCHAR(100),
    provider_id     UUID,
    diagnosis_code  VARCHAR(20),           -- ICD-10
    reason_code     VARCHAR(20),
    notes           TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Clinical observations (vitals, labs, symptoms)
CREATE TABLE observations (
    observation_id  UUID PRIMARY KEY,
    patient_id      UUID NOT NULL REFERENCES patients(patient_id),
    encounter_id    UUID REFERENCES encounters(encounter_id),
    code            VARCHAR(20) NOT NULL,   -- LOINC code
    value           TEXT NOT NULL,
    unit            VARCHAR(50),
    interpretation  VARCHAR(20),           -- 'normal', 'high', 'low', 'critical'
    reference_range VARCHAR(100),
    status          VARCHAR(20) NOT NULL,  -- 'preliminary', 'final', 'corrected'
    observed_at     TIMESTAMP NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Conditions / diagnoses
CREATE TABLE conditions (
    condition_id    UUID PRIMARY KEY,
    patient_id      UUID NOT NULL REFERENCES patients(patient_id),
    encounter_id    UUID REFERENCES encounters(encounter_id),
    code            VARCHAR(20) NOT NULL,   -- ICD-10 or SNOMED
    description     VARCHAR(500),
    onset_date      DATE,
    resolution_date DATE,
    clinical_status VARCHAR(50),           -- 'active', 'resolved', 'remission'
    severity        VARCHAR(20),            -- 'mild', 'moderate', 'severe'
    verified_by     UUID,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Medications
CREATE TABLE medications (
    medication_id   UUID PRIMARY KEY,
    patient_id      UUID NOT NULL REFERENCES patients(patient_id),
    encounter_id    UUID REFERENCES encounters(encounter_id),
    rxnorm_code     VARCHAR(20),           -- RxNorm identifier
    name            VARCHAR(255) NOT NULL,
    dosage          VARCHAR(100),
    route           VARCHAR(50),           -- 'oral', 'IV', 'topical'
    frequency       VARCHAR(100),
    start_date      DATE NOT NULL,
    end_date        DATE,
    prescriber_id   UUID,
    status          VARCHAR(20),           -- 'active', 'completed', 'stopped'
    reason_code     VARCHAR(20),
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Key indexes for performance
CREATE INDEX idx_encounters_patient ON encounters(patient_id, start_time DESC);
CREATE INDEX idx_observations_patient_code ON observations(patient_id, code, observed_at DESC);
CREATE INDEX idx_conditions_patient ON conditions(patient_id);
CREATE INDEX idx_medications_patient ON medications(patient_id, start_date DESC);
```

### Coded Terminology Standards

| Standard | Purpose | Example |
|---|---|---|
| **ICD-10** | Diagnosis codes | `I10` = Essential hypertension |
| **LOINC** | Lab tests & observations | `2951-2` = Sodium level in blood |
| **SNOMED CT** | Clinical concepts | `73211009` = Diabetes mellitus |
| **RxNorm** | Medication names | `860999` = Atorvastatin 20mg |
| **CPT** | Procedure codes | `99213` = Office visit, established |
| **NDC** | Drug packaging | `0002-1427-01` |

---

## 3. HL7 FHIR Interoperability

### FHIR Resources

```
┌─────────────────────────────────────┐
│          FHIR RESOURCES             │
│                                      │
│  Patient Administration:             │
│  ┌────────┐ ┌──────────┐ ┌────────┐ │
│  │Patient │ │Organization│ │Location│ │
│  └────────┘ └──────────┘ └────────┘ │
│                                      │
│  Clinical:                           │
│  ┌─────┐ ┌─────┐ ┌────────┐ ┌─────┐ │
│  │Cond-│ │Ob-  │ │Medi-   │ │Care-│ │
│  │ition│ │serv.│ │cation  │ │Plan │ │
│  └─────┘ └─────┘ └────────┘ └─────┘ │
│                                      │
│  Diagnostics:                        │
│  ┌──────────┐ ┌─────────┐ ┌───────┐ │
│  │Diagnostic│ │Imaging- │ │Speci- │ │
│  │ Report   │ │ Study   │ │men    │ │
│  └──────────┘ └─────────┘ └───────┘ │
│                                      │
│  Workflow:                           │
│  ┌─────────┐ ┌───────┐ ┌──────────┐ │
│  │Encount- │ │Task   │ │Appoint-  │ │
│  │ er      │ │       │ │ ment     │ │
│  └─────────┘ └───────┘ └──────────┘ │
└─────────────────────────────────────┘
```

### FHIR REST API Pattern

```typescript
// HL7 FHIR API implementation
interface FHIRResource {
  resourceType: string;
  id: string;
  meta: {
    versionId: string;
    lastUpdated: string;
    security?: Coding[];
  };
  identifier?: Identifier[];
}

interface Patient extends FHIRResource {
  resourceType: 'Patient';
  identifier: Identifier[];
  name: HumanName[];
  gender: 'male' | 'female' | 'other' | 'unknown';
  birthDate: string;
  deceasedBoolean?: boolean;
  address?: Address[];
  telecom?: ContactPoint[];
  generalPractitioner?: Reference[];
}

interface Observation extends FHIRResource {
  resourceType: 'Observation';
  status: 'final' | 'preliminary' | 'corrected' | 'cancelled';
  code: CodeableConcept;      // LOINC
  subject: Reference;         // Patient reference
  effectiveDateTime: string;
  valueQuantity?: Quantity;
  valueCodeableConcept?: CodeableConcept;
  interpretation?: CodeableConcept[];
  referenceRange?: {
    low?: Quantity;
    high?: Quantity;
    text?: string;
  }[];
}

class FHIRServer {
  constructor(private db: Database.Database) {}

  // Read resource by ID
  readResource(resourceType: string, id: string): FHIRResource | null {
    const row = this.db.prepare(
      `SELECT resource FROM fhir_resources WHERE resource_type = ? AND id = ?`
    ).get(resourceType, id) as any;

    return row ? JSON.parse(row.resource) : null;
  }

  // Search (simplified)
  searchResource(resourceType: string, params: Record<string, string>): FHIRResource[] {
    let query = 'SELECT resource FROM fhir_resources WHERE resource_type = ?';
    const queryParams: unknown[] = [resourceType];

    // Build search filters
    for (const [key, value] of Object.entries(params)) {
      if (key === 'family') {
        query += ` AND resource->>'$.name[0].family' LIKE ?`;
        queryParams.push(`%${value}%`);
      } else if (key === 'birthdate') {
        query += ` AND resource->>'$.birthDate' = ?`;
        queryParams.push(value);
      } else if (key === 'code') {
        query += ` AND resource->>'$.code.coding[0].code' = ?`;
        queryParams.push(value);
      }
    }

    const rows = this.db.prepare(query).all(...queryParams) as any[];
    return rows.map(r => JSON.parse(r.resource));
  }

  // Create resource
  createResource(resourceType: string, resource: FHIRResource): FHIRResource {
    const id = crypto.randomUUID();
    resource.id = id;
    resource.meta = {
      versionId: '1',
      lastUpdated: new Date().toISOString(),
    };

    this.db.prepare(`
      INSERT INTO fhir_resources (resource_type, id, resource, created_at)
      VALUES (?, ?, ?, datetime('now'))
    `).run(resourceType, id, JSON.stringify(resource));

    return resource;
  }

  // Update resource (versioned)
  updateResource(resourceType: string, id: string, resource: FHIRResource): FHIRResource {
    const existing = this.readResource(resourceType, id);
    if (!existing) throw new Error('Not Found');

    resource.meta = {
      ...resource.meta,
      versionId: String(parseInt(existing.meta.versionId) + 1),
      lastUpdated: new Date().toISOString(),
    };

    this.db.prepare(`
      UPDATE fhir_resources SET resource = ?, updated_at = datetime('now')
      WHERE resource_type = ? AND id = ?
    `).run(JSON.stringify(resource), resourceType, id);

    return resource;
  }
}
```

---

## 4. HIPAA Compliance

### Key Requirements

| Rule | Requirement | Implementation |
|---|---|---|
| **Privacy Rule** | Protected Health Information (PHI) must be protected | Encryption at rest & transit, access controls |
| **Security Rule** | Administrative, physical, technical safeguards | Audit logs, authentication, encryption |
| **Breach Notification** | Notify patients of breaches | Automated detection & notification system |
| **Omnibus Rule** | Business Associate Agreements | BA contracts, downstream compliance |

### HIPAA-Compliant Audit Log

```sql
CREATE TABLE audit_log (
    audit_id        UUID PRIMARY KEY,
    user_id         UUID NOT NULL,
    patient_id      UUID,
    action          VARCHAR(50) NOT NULL,  -- 'view', 'create', 'update', 'delete', 'export'
    resource_type   VARCHAR(50),           -- 'patient', 'observation', 'condition'
    resource_id     VARCHAR(100),
    ip_address      INET NOT NULL,
    user_agent      VARCHAR(500),
    details         JSONB,                 -- What changed (never PHI in details)
    timestamp       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Required for HIPAA: immutable audit trail
CREATE INDEX idx_audit_patient ON audit_log(patient_id, timestamp DESC);
CREATE INDEX idx_audit_user ON audit_log(user_id, timestamp DESC);
CREATE INDEX idx_audit_timestamp ON audit_log(timestamp);
```

### Access Control & Data Segmentation

```typescript
// Healthcare-specific authorization
interface AuthorizationContext {
  userId: string;
  role: 'physician' | 'nurse' | 'admin' | 'patient' | 'researcher';
  department: string;
  patientRelationships: string[];  // 'primary_care', 'attending', 'consult'
}

function checkAccess(context: AuthorizationContext, patientId: string, resourceType: string): boolean {
  // 1. Patients can access their own data
  if (context.role === 'patient' && context.userId === patientId) {
    return true;
  }

  // 2. Clinicians need a treatment relationship
  if (['physician', 'nurse'].includes(context.role)) {
    return context.patientRelationships.includes(patientId);
  }

  // 3. Admins — limited to scheduling/billing (no clinical data)
  if (context.role === 'admin') {
    return ['encounter', 'appointment'].includes(resourceType);
  }

  // 4. Researchers — de-identified data only
  if (context.role === 'researcher') {
    return false; // Must go through de-identification pipeline
  }

  return false;
}

// Data masking for display
function maskPHI(data: Patient, viewerRole: string): Partial<Patient> {
  const masked = { ...data };

  if (viewerRole !== 'physician') {
    // Mask SSN/identifiers for non-clinicians
    masked.identifier = masked.identifier.map(id => ({
      ...id,
      value: id.value.replace(/.(?=.{4})/g, '*'),  // Show last 4 only
    }));
  }

  if (viewerRole === 'patient') {
    // Remove financial data, internal notes
    delete (masked as any).internalNotes;
    delete (masked as any).billingCodes;
  }

  if (viewerRole === 'researcher') {
    // Remove all 18 HIPAA identifiers
    delete masked.name;
    delete masked.birthDate;
    delete (masked as any).ssn;
    // ... remove all direct identifiers
  }

  return masked;
}
```

---

## 5. Medical Imaging (DICOM)

### DICOM Architecture

```
Modality (Scanner)
    │  (DICOM protocol)
    ▼
┌──────────────┐
│  DICOM Node  │  C-STORE, C-FIND, C-MOVE, C-GET
└──────┬───────┘
       │
┌──────▼───────┐
│   PACS       │  Image Archive
│   (DICOM)    │
└──────┬───────┘
       │
┌──────▼───────┐
│  Viewer /    │  DICOMweb, WADO
│  Workstation │
└──────────────┘
```

### Medical Imaging Pipeline

```python
# Medical image processing pipeline
import numpy as np
import pydicom
from PIL import Image
import io

def process_dicom_image(dicom_path: str) -> dict:
    """Process DICOM file and return pixel data + metadata."""
    ds = pydicom.dcmread(dicom_path)

    # Extract pixel data
    pixel_array = ds.pixel_array

    # Apply modality-specific transformations
    if ds.Modality == 'CT':
        # CT: Hounsfield Units conversion
        intercept = ds.RescaleIntercept
        slope = ds.RescaleSlope
        hu_array = pixel_array * slope + intercept
        pixel_array = hu_array
    elif ds.Modality == 'MR':
        # MRI: normalize to 0-1
        pixel_array = pixel_array.astype(float) / pixel_array.max()

    # Window level/width adjustment
    window_center = ds.WindowCenter
    window_width = ds.WindowWidth
    if hasattr(window_center, '__iter__'):
        window_center = window_center[0]
        window_width = window_width[0]

    lower = window_center - window_width / 2
    upper = window_center + window_width / 2
    windowed = np.clip(pixel_array, lower, upper)
    windowed = ((windowed - lower) / (upper - lower) * 255).astype(np.uint8)

    return {
        'pixel_data': windowed,
        'metadata': {
            'study_uid': ds.StudyInstanceUID,
            'series_uid': ds.SeriesInstanceUID,
            'modality': ds.Modality,
            'body_part': ds.BodyPartExamined if hasattr(ds, 'BodyPartExamined') else 'unknown',
            'rows': ds.Rows,
            'columns': ds.Columns,
            'pixel_spacing': list(ds.PixelSpacing) if hasattr(ds, 'PixelSpacing') else None,
            'bit_depth': ds.BitsStored,
        }
    }

def convert_to_png(dicom_path: str, output_path: str) -> None:
    """Convert DICOM to viewable PNG."""
    result = process_dicom_image(dicom_path)
    img = Image.fromarray(result['pixel_data'])
    img.save(output_path, 'PNG')

def anonymize_dicom(dicom_path: str, output_path: str) -> None:
    """Remove PHI from DICOM file."""
    ds = pydicom.dcmread(dicom_path)

    # Remove all patient identifiers
    tags_to_clear = [
        (0x0010, 0x0010),  # Patient's Name
        (0x0010, 0x0020),  # Patient ID
        (0x0010, 0x0030),  # Patient's Birth Date
        (0x0010, 0x0040),  # Patient's Sex
        (0x0010, 0x1000),  # Other Patient IDs
        (0x0008, 0x0080),  # Institution Name
        (0x0008, 0x0090),  # Referring Physician
        (0x0008, 0x1050),  # Performing Physician
    ]

    for tag in tags_to_clear:
        if tag in ds:
            ds[tag].value = ''

    ds.save_as(output_path)
```

---

## Quick Reference: Healthcare by Node Type

| Node Type | Healthcare Mapping |
|---|---|
| **Input** | Patient intake form, lab results import, medical device data, FHIR API request |
| **Logic** | Clinical decision support, drug interaction check, HL7 message parsing, claims adjudication |
| **Database** | EHR clinical data store, FHIR resource repository, medical image archive |
| **UI** | Patient portal, clinical dashboard, EMR viewer, scheduling interface |
| **API** | FHIR REST endpoints, HL7 v2 message handler, DICOMweb, interoperability gateway |

---

*For deeper healthcare concepts, see Bible level `39-healthcare-life-sciences/` — EHR systems, FHIR, medical imaging, telehealth, analytics, and pharma/genomics.*
