# frozen_string_literal: true

require "json"

module Eve
  module Provider
    def self.provider_id_from_path
      prog = File.expand_path($PROGRAM_NAME)
      match = prog.match(%r{plugins/providers/([^/]+)/commands/provider-command\z})
      match ? match[1] : nil
    end

    def self.dispatch(argv)
      command = argv.shift
      extra_args = argv

      unless command
        warn "Usage: #{File.basename($PROGRAM_NAME)} <command> [args...]"
        exit 2
      end

      resolved = begin
        Eve::SDK::Resolve.from_env
      rescue Eve::SDK::SchemaValidationError => e
        warn "provider-command: #{e.message}"
        exit 1
      rescue Eve::SDK::ContractError => e
        warn "provider-command: #{e.message}"
        exit 1
      end

      begin
        Eve::SDK::Contract.validate_input!(resolved.raw)
      rescue Eve::SDK::ContractError => e
        warn "provider-command: #{e.message}"
        exit 1
      end

      provider_id = ENV["EVE_PROVIDER_PLUGIN"] || provider_id_from_path
      instance_name = resolved.instance_name
      engine = resolved.engine

      if resolved.provider != provider_id
        warn "provider-command: dispatch provider #{provider_id} does not match resolved provider #{resolved.provider}"
        exit 1
      end

      if ENV["EVE_PLUGIN_DRY_RUN"] == "1" || command == "resolve"
        payload = {
          "kind" => "provider",
          "provider" => provider_id,
          "command" => command,
          "instance" => instance_name,
          "profile" => instance_name,
          "engine" => engine,
          "dry_run" => ENV["EVE_PLUGIN_DRY_RUN"] == "1"
        }
        begin
          Eve::SDK::Contract.validate_output!(payload, def_name: "provider_command_output")
        rescue Eve::SDK::ContractError => e
          warn "provider-command: #{e.message}"
          exit 1
        end
        puts JSON.generate(payload)
        exit 0
      end

      root = Eve::SDK::Workdir.repo_root

      case command
      when "init"
        if engine == "metal"
          warn "[init] instance=#{instance_name} uses metal hardware; no Terraform backend to initialize."
          exit 0
        end
        exec File.join(root, "scripts", "tf-init"), instance_name
      when "plan"
        case engine
        when "vagrant"
          exec File.join(root, "scripts", "vagrant-up"), "--plan", instance_name
        when "metal"
          warn "[plan] instance=#{instance_name} uses metal hardware; provisioning will run over SSH."
          exec File.join(root, "scripts", "profile-resolve"), "--profile", instance_name, "--emit", "env"
        else
          exec File.join(root, "scripts", "tf-plan"), instance_name
        end
      when "up"
        case engine
        when "vagrant"
          exec File.join(root, "scripts", "vagrant-up"), instance_name
        when "metal"
          warn "[up] instance=#{instance_name} uses metal hardware; nothing to create."
          exit 0
        else
          exec File.join(root, "scripts", "tf-apply"), instance_name
        end
      when "down"
        case engine
        when "vagrant"
          exec File.join(root, "scripts", "vagrant-destroy"), instance_name
        when "metal"
          warn "[down] instance=#{instance_name} uses metal hardware; nothing to destroy."
          exit 0
        else
          exec File.join(root, "scripts", "tf-destroy"), instance_name
        end
      when "start", "stop", "status"
        exec File.join(root, "scripts", command), instance_name
      when "ip"
        exec File.join(root, "scripts", "instance-ip"), instance_name
      when "ssh"
        exec File.join(root, "scripts", "instance-ssh"), instance_name, *extra_args
      else
        warn "provider-command: unsupported command: #{command}"
        exit 2
      end
    end
  end
end
