stack {
  name = "201 Shared"

  tags = [
    "vultr",
    "shared",
    "networking",
  ]

  after = [
    "/stacks/vultr/10-base",
  ]
}

generate_hcl "allowed-cidrs.tf" {
  content {
    variable "my_ip" {
      type = string
    }

    locals {
      allowed_cidrs = ["${var.my_ip}/32"]
    }
  }
}

import {
  source = "/modules/vultr/ec2/vpc.tm.hcl"
}

import {
  source = "/modules/vultr/ec2/security_group.tm.hcl"
}
