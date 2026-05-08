globals {
  terraform_version = "~> 1.14.9"
  project           = "ephemeral-cloud-gaming"
}

globals "gcp" {
  labels = {
    project    = global.project
    managed_by = "terraform"
  }
}
