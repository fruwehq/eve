globals {
  terraform_version = ">= 1.14.9, < 1.16.0"
  project           = "ephemeral-cloud-gaming"
}

globals "gcp" {
  labels = {
    project    = global.project
    managed_by = "terraform"
  }
}
