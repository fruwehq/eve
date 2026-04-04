// TERRAMATE: GENERATED AUTOMATICALLY DO NOT EDIT

variable "my_ip" {
  type = "string"
}
locals {
  allowed_cidrs = [
    "${var.my_ip}/32",
  ]
}
