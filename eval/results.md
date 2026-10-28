# FinePrint evaluation results

12 documents, 64 gold risk labels. Model: none (rules only).

| Method | Split | Precision | Recall | F1 | TP | FP | FN |
| --- | --- | --- | --- | --- | --- | --- | --- |
| rules | dev | 1.00 | 1.00 | 1.00 | 47 | 0 | 0 |
| rules | test | 0.93 | 0.77 | 0.84 | 13 | 1 | 4 |
| rules | all | 0.98 | 0.94 | 0.96 | 60 | 1 | 4 |

## Per category (all documents)

| Category | rules F1 |
| --- | --- |
| prepayment_penalty | 1.00 |
| floating_rate | 0.86 |
| late_payment | 1.00 |
| bounce_charge | 1.00 |
| processing_fee | 1.00 |
| auto_renewal | 0.80 |
| deferred_interest | 1.00 |
| bundled_insurance | 1.00 |
| unilateral_change | 1.00 |
| set_off_lien | 0.89 |
| data_sharing | 1.00 |
| insurance_exclusion | 0.93 |
| recurring_fee | 1.00 |
| minimum_due | 0.86 |

Pre-filled loan numbers correct: 21 of 23.

Flesch reading ease of explanations (higher is easier): Simple = 88.7, Expert = 68.2.

## Errors (last method)

```
FN  s09 set_off_lien         recovered from any bank account linked
FN  s11 minimum_due          interest-free period of up to 50 days is not available
FP  s12 floating_rate        C6: 4. The insurer may revise premium rates at renewal with the approval of the regulator.
FN  s12 auto_renewal         renews each year on the policy anniversary
FN  s12 insurance_exclusion  A deductible of Rs. 5,000
CTX s09 principal: expected 25000, got None
CTX s10 annual_rate: expected 11.75, got 2.5
```
