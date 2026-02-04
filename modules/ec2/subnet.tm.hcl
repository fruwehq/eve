generate_hcl "z_ec2_subnet.tf" {
  content {
    data "aws_subnets" "default" {
      filter {
        name   = "vpc-id"
        values = [aws_default_vpc.default.id]
      }

      filter {
        name   = "default-for-az"
        values = ["true"]
      }
    }

    locals {
      default_vpc_id   = aws_default_vpc.default.id
      default_subnet_id = data.aws_subnets.default.ids[0]
    }

    output "vpc_id" {
      value = local.default_vpc_id
    }

    output "subnet_id" {
      value = local.default_subnet_id
    }
  }
}
