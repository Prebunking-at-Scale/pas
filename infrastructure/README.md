# PAS /infrastructure
Terraform and other infrastructure config for the Prebunking at Scale project

## Getting Started

### Prerequisites

This is a fairly standard terraform repository. If you've never used terraform with GCP before, you will likely need to authenticate.
A guide to do so [is provided by Google](https://cloud.google.com/docs/terraform/authentication).

### Configuration

1. Initialize Terraform:
  Navigate to the desired environment (e.g., `dev`) and run:
  ```sh
  cd terraform/environments/dev
  terraform init
  ```

2. Configure tfvars:
  You might have to source the tfvars from someone as they currently contain secrets and we're not committing those.
  ```sh
  $EDITOR terraform.tfvars  # make your changes, or preferably don't
  ```

3. Plan the deployment:
  ```sh
  terraform plan -o "tfplan"
  ```

4. Apply the plan:
  ```sh
  terraform apply "tfplan"
  ```

## Notes

### pgvector

The PostgresQL instance should be running pgvector as necessary for the rest of the PAS work.
On Cloud SQL the extension is already installed and just needs to be enabled on the database.
To enable pgvector, log in to the instance as a user with appropriate permissions, choose your database and run:

```sql
CREATE EXTENSION vector;
```
