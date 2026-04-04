stack {
  name = "301 Windows"

  tags = [
    "aws",
    "services",
    "windows",
  ]

  after = [
    "/stacks/aws/20-shared",
  ]
}

globals {
  availability_zone = "ap-northeast-1b"
  instance_type     = "g5.2xlarge"
  # instance_type  = "g5.xlarge"
  # instance_type  = "g5.4xlarge"
  # instance_type  = "g4dn.2xlarge"
  use_spot = true
}

import {
  source = "/modules/ec2/instance.tm.hcl"
}
