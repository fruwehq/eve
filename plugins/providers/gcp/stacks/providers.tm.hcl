generate_hcl "z_providers.tf" {
  content {
    terraform {
      required_providers {
        google = {
          source  = "hashicorp/google"
          version = "7.12.0"
        }
      }

      required_version = global.terraform_version
    }

    variable "project_id" {
      type        = string
      description = "GCP project id (from GOOGLE_CLOUD_PROJECT/GOOGLE_PROJECT)"
    }

    variable "region" {
      type        = string
      description = "GCP region (from catalog location mapping)"
    }

    variable "zone" {
      type        = string
      description = "GCP zone (from catalog location mapping)"
    }

    provider "google" {
      project = var.project_id
      region  = var.region
      zone    = var.zone
    }
  }
}
