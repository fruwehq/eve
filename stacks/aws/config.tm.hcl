globals "aws" {
  # Region is resolved per-profile via TF_VAR_region (set by scripts/profile-tf-env
  # from config/catalog.yaml location mapping). Do not hardcode here.
  tags = {
    Project   = global.project
    ManagedBy = "terraform"
  }
}
