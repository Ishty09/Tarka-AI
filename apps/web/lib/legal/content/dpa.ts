import type { LocalisedContent } from "../types";

const en = `# Data Processing Agreement

This Data Processing Agreement ("DPA") supplements our [Terms of Service](/legal/terms/en) and applies where Quarrel AI processes personal data on your behalf in a business-to-business context — for example, where you have purchased Quarrel for use across a team or organisation under a future B2B plan, or where you act as a controller for end-users who interact with your Quarrel deployment.

Quarrel's B2B plan is **not yet launched**. This page exists so prospective business customers can review the terms in advance and so privacy and procurement teams can attach this DPA to a request for proposal. We will negotiate reasonable amendments on signed agreements.

## 1. Roles

In the context of this DPA:

- You ("Customer") are the **controller** of personal data submitted to the Service by you and by end-users you authorise (your employees, contractors, members, students, etc.).
- Quarrel is the **processor** of that personal data, processing it solely to provide the Service under our agreement.

Where Quarrel acts as an independent controller — for example, for our own billing relationship with you, our security and fraud-prevention activities, or aggregated product analytics — our [Privacy Policy](/legal/privacy/en) governs.

## 2. Subject matter and duration

- **Subject matter**: processing necessary to provide the Service described in our agreement with you.
- **Duration**: the term of our agreement plus any post-termination period required for return or deletion of personal data.
- **Nature and purpose**: hosting, transmission, retrieval, and AI-assisted processing of Customer Personal Data to operate the chat, memory, social, and commitment features.

## 3. Categories of data and data subjects

- **Categories of personal data**: identifiers (email, username), authentication tokens, conversation content, extracted facts, locale and device data, payment metadata.
- **Categories of data subjects**: Customer's end-users (employees, contractors, members, etc.).
- **Special category data**: may appear in conversation content if end-users send it. Customer is responsible for confirming the lawful basis for that processing.

## 4. Quarrel's obligations

We will:

- Process Customer Personal Data only on documented instructions from Customer (the instructions in our agreement, the configuration choices Customer makes in the Service, and reasonable instructions Customer sends in writing).
- Ensure persons authorised to process Customer Personal Data are under a confidentiality obligation.
- Implement appropriate technical and organisational measures (see §7 below) and assist Customer with security obligations.
- Assist Customer in responding to data subject requests as described in §6.
- Notify Customer without undue delay (and, where the GDPR applies, within 72 hours of becoming aware) of any Personal Data Breach affecting Customer Personal Data, with the information Customer needs to meet its own breach-notification obligations.
- At Customer's choice, delete or return Customer Personal Data on termination, subject to legal-hold exceptions.
- Make available the information necessary to demonstrate compliance with this DPA and allow audits by Customer or an auditor mandated by Customer, no more than once per twelve-month period absent a documented breach.

## 5. Subprocessors

Customer authorises Quarrel to engage the subprocessors listed in our public subprocessor list (currently the providers in §4 of our [Privacy Policy](/legal/privacy/en)). We give Customer at least 30 days' notice before adding a new subprocessor. Customer may object on reasonable data-protection grounds; we will discuss alternatives in good faith and, if no resolution is found, Customer may terminate the affected Service with refund of pre-paid fees for the unused term.

Quarrel imposes data-protection obligations on each subprocessor that are no less protective than those in this DPA, and remains liable to Customer for the subprocessor's acts and omissions.

## 6. Data subject rights and authority requests

Quarrel will:

- Provide reasonable technical and organisational measures to assist Customer in responding to requests from data subjects exercising their rights under the GDPR or equivalent.
- Inform Customer promptly (and not respond directly) if Quarrel receives a request from a data subject relating to Customer Personal Data, except where Quarrel is legally compelled to respond.
- Notify Customer of legally binding requests from public authorities relating to Customer Personal Data unless the law prohibits such notification.

## 7. Security measures

A current list of technical and organisational measures is available on request. At minimum, we maintain:

- Row-level security on every database table, scoped service-role keys, parameterised SQL only.
- TLS 1.2+ for all data in transit; encryption at rest for the production database and backups.
- HMAC-verified webhooks; rate limiting at the gateway and application layers.
- Quarterly secret rotation; structured access logs.
- Documented backup, restore, and incident-response procedures.
- Background checks for personnel with administrative access, where local law permits.

## 8. International transfers

Customer Personal Data may be transferred to the United States and other countries where our subprocessors are located. Transfers from the EEA, UK, or Switzerland rely on the European Commission's Standard Contractual Clauses (2021), Module 2 (controller to processor) and Module 3 (processor to subprocessor) as applicable, incorporated by reference into this DPA and signed on Customer's behalf upon execution of our agreement. Transfer impact assessments are available on request.

## 9. Liability

Liability under this DPA is subject to the limitation of liability in our agreement with Customer.

## 10. Order of precedence

In case of conflict, the order is: (1) the data protection laws applicable to Customer; (2) this DPA; (3) the agreement between Customer and Quarrel; (4) the [Privacy Policy](/legal/privacy/en) for matters where Quarrel acts as a controller.

## 11. Contact

DPA matters: **dpa@quarrel.ai**.
Data Protection Officer: **dpo@quarrel.ai**.

To execute this DPA against a forthcoming B2B agreement, contact us at the email above with your entity name, jurisdiction, and the email of the signatory.
`;

export const dpa: LocalisedContent = {
  en: {
    title: "Data Processing Agreement",
    lastUpdated: "2026-05-21",
    summary:
      "Quarrel's processor-side commitments for forthcoming B2B engagements — SCCs, subprocessors, security measures, audit rights.",
    markdown: en,
  },
  bn: null,
  hi: null,
  es: null,
  pt: null,
  ar: null,
};
