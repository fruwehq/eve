stack {
  name = "AWS Shared Networking"

  tags = [
    "aws",
    "aws-shared",
    "networking",
    "shared",
  ]
}

generate_hcl "z_allowed-cidrs.tf" {
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
  source = "/modules/aws/ec2/vpc.tm.hcl"
}

import {
  source = "/modules/aws/ec2/security_group.tm.hcl"
}
