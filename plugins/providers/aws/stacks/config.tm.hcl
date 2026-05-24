globals {
  terraform_version = ">= 1.14.9, < 1.16.0"
  project           = "ephemeral-cloud-gaming"
}

globals "aws" {
  # Region is resolved per-profile via TF_VAR_region (set by scripts/profile-tf-env
  # from config/catalog.yaml location mapping). Do not hardcode here.
  tags = {
    Project   = global.project
    ManagedBy = "terraform"
  }
}
