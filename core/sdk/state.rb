# frozen_string_literal: true

require "json"
require "time"
require "fileutils"

module Egame
  module SDK
    class StateError < StandardError; end

    module State
      OPERATION_STATUSES = %w[running succeeded failed skipped].freeze
      DESIRED_STATES = %w[unknown running stopped absent].freeze
      PROVIDER_STATES = %w[unknown initializing initialized planned changing running stopped absent error].freeze
      PROVISION_STATES = %w[unknown provisioning provisioned error].freeze
      PACKAGE_STATES = %w[unknown installed missing failed removed reinstalled].freeze
      DEFAULT_HISTORY_LIMIT = 50

      def self.lock_path(instance_name)
        File.join(Workdir.state_base, "instances", "#{instance_name}.lock")
      end

      def self.with_read_lock(instance_name)
        lp = lock_path(instance_name)
        Workdir.ensure_dir(File.dirname(lp))
        File.open(lp, File::RDWR | File::CREAT, 0o600) do |f|
          f.flock(File::LOCK_SH)
          yield
        end
      end

      def self.with_write_lock(instance_name)
        lp = lock_path(instance_name)
        Workdir.ensure_dir(File.dirname(lp))
        File.open(lp, File::RDWR | File::CREAT, 0o600) do |f|
          f.flock(File::LOCK_EX)
          yield
        end
      end

      def self.read(instance_name)
        path = Workdir.state_path(instance_name)
        with_read_lock(instance_name) do
          stored = if File.exist?(path)
                     raw = File.read(path)
                     raw.empty? ? {} : JSON.parse(raw)
                   else
                     {}
                   end
          merged = default_state(instance_name).merge(stored)
          merged["package_state"] ||= {}
          merged["observed_state"] ||= {}
          merged["operation_history"] ||= []
          validate_state!(merged)
          merged
        end
      rescue JSON::ParserError => e
        raise StateError, "Cannot parse state for #{instance_name}: #{e.message}"
      end

      def self.validate_state!(state)
        require "json_schemer"
        schema_path = File.join(File.expand_path("../schema", __dir__), "observed-state.schema.json")
        schema = begin
          JSON.parse(File.read(schema_path))
        rescue Errno::ENOENT
          raise SchemaValidationError, "Schema file not found: #{schema_path}"
        end
        schemer = JSONSchemer.schema(schema)
        errors = schemer.validate(state).to_a
        return if errors.empty?

        lines = ["Observed state failed schema validation:"]
        errors.each do |err|
          ptr = err["data_pointer"]
          detail = err["error"] || err["type"].to_s
          lines << "  #{ptr.empty? ? "/" : ptr}: #{detail}"
        end
        raise SchemaValidationError, lines.join("\n")
      end

      def self.write(instance_name, state)
        path = Workdir.state_path(instance_name)
        dir = File.dirname(path)
        Workdir.ensure_dir(dir)
        with_write_lock(instance_name) do
          validate_state!(state)
          atomic_write(path, state)
        end
        state
      end

      def self.atomic_write(path, state)
        dir = File.dirname(path)
        basename = File.basename(path)
        tmp = File.join(dir, ".#{basename}.tmp.#{$$}")
        File.write(tmp, JSON.pretty_generate(state) + "\n")
        File.rename(tmp, path)
      rescue StandardError
        File.delete(tmp) if File.exist?(tmp)
        raise
      end

      def self.modify(instance_name)
        path = Workdir.state_path(instance_name)
        dir = File.dirname(path)
        Workdir.ensure_dir(dir)
        lp = lock_path(instance_name)
        Workdir.ensure_dir(File.dirname(lp))

        File.open(lp, File::RDWR | File::CREAT, 0o600) do |lock|
          lock.flock(File::LOCK_EX)

          stored = if File.exist?(path)
                     raw = File.read(path)
                     raw.empty? ? {} : JSON.parse(raw)
                   else
                     {}
                   end
          state = default_state(instance_name).merge(stored)
          state["package_state"] ||= {}
          state["observed_state"] ||= {}
          state["operation_history"] ||= []

          state = yield(state)

          validate_state!(state)
          atomic_write(path, state)
          state
        end
      rescue JSON::ParserError => e
        raise StateError, "Cannot parse state for #{instance_name}: #{e.message}"
      end

      def self.default_state(instance_name, now = nil)
        state = {
          "instance" => instance_name,
          "desired_state" => "unknown",
          "provider_state" => "unknown",
          "provision_state" => "unknown",
          "package_state" => {},
          "observed_state" => {},
          "operation_history" => [],
          "last_operation" => nil,
          "last_error" => nil
        }
        state["created_at"] = now if now
        state["updated_at"] = now if now
        state
      end

      def self.record_operation(instance_name, operation, status, error: nil,
                                desired_state: nil, provider_state: nil,
                                provision_state: nil, package: nil, package_state: nil)
        validate_enum!(status, OPERATION_STATUSES, "status")
        validate_enum!(desired_state, DESIRED_STATES, "desired_state") if desired_state
        validate_enum!(provider_state, PROVIDER_STATES, "provider_state") if provider_state
        validate_enum!(provision_state, PROVISION_STATES, "provision_state") if provision_state
        validate_enum!(package_state, PACKAGE_STATES, "package_state") if package_state

        now = Time.now.utc.iso8601

        modify(instance_name) do |state|
          state["created_at"] ||= now
          state["updated_at"] = now

          entry = {
            "id" => state["operation_history"].length + 1,
            "name" => operation,
            "type" => operation.split(".", 2).first,
            "status" => status,
            "at" => now
          }
          state["last_operation"] = entry
          state["operation_history"] << entry.merge("error" => error).compact
          state["operation_history"] = state["operation_history"].last(history_limit)
          state["last_error"] = error
          state["desired_state"] = desired_state if desired_state
          state["provider_state"] = provider_state if provider_state
          state["provision_state"] = provision_state if provision_state

          if package && package_state
            state["package_state"][package] = {
              "status" => package_state,
              "updated_at" => now
            }
          end

          state
        end
      end

      def self.update_observed(instance_name, observed)
        now = Time.now.utc.iso8601

        modify(instance_name) do |state|
          state["observed_state"] = state.fetch("observed_state", {}).merge(observed)
          state["updated_at"] = now
          state
        end
      end

      def self.recover_running(instance_name)
        now = Time.now.utc.iso8601

        modify(instance_name) do |state|
          last_op = state["last_operation"]
          if last_op && last_op["status"] == "running"
            err = "Recovered interrupted operation #{last_op.fetch("name", "unknown")}"
            recovered = last_op.merge("status" => "failed", "error" => err)
            state["last_operation"] = recovered
            state["last_error"] = err
            state["updated_at"] = now
            state["operation_history"] = state.fetch("operation_history").map do |entry|
              entry["id"] == recovered["id"] ? entry.merge("status" => "failed", "error" => err) : entry
            end
            case recovered["type"]
            when "provider"
              state["provider_state"] = "error" unless %w[provider.resolve provider.status provider.ip provider.ssh].include?(recovered["name"])
            when "provision"
              state["provision_state"] = "error"
            end
          end

          state
        end
      end

      def self.build_view(instance_name:, resolved:, packages:, paths:)
        state = read(instance_name)
        package_state = state.fetch("package_state", {})

        observed = state.fetch("observed_state", {})
        reconciled_state = StateMachine.status_with_observed_state(
          { "state" => state, "observed_state" => observed },
          { "observed_state" => observed }
        ).fetch("state", state)

        enriched_packages = packages.map do |pkg|
          pkg.merge("state" => package_state.fetch(pkg.fetch("id"), { "status" => "unknown" }))
        end
        selected_packages = enriched_packages.select { |p| p["selected"] }

        package_summary = selected_packages.each_with_object(Hash.new(0)) do |pkg, summary|
          summary[pkg.dig("state", "status") || "unknown"] += 1
        end
        PACKAGE_STATES.each do |status_key|
          package_summary[status_key] = package_summary.fetch(status_key, 0)
        end

        eps = StateMachine.effective_provider_state(reconciled_state)
        paa = StateMachine.provider_actions_available(reconciled_state)
        reconciled_state["effective_provider_state"] = eps
        reconciled_state["provider_actions_available"] = paa

        {
          "instance" => {
            "name" => instance_name,
            "provider" => resolved.dig("machine", "provider"),
            "provider_plugin" => resolved["provider_plugin"],
            "engine" => resolved["engine"],
            "machine" => resolved.dig("composition", "machine"),
            "os" => resolved.dig("os", "id"),
            "os_family" => resolved.dig("os", "family"),
            "location" => resolved.dig("location", "name"),
            "bundles" => resolved.dig("composition", "bundles") || [],
            "access" => resolved.fetch("access", {})
          },
          "state" => reconciled_state,
          "observed_state" => reconciled_state.fetch("observed_state", {}),
          "effective_provider_state" => eps,
          "provider_actions_available" => paa,
          "packages" => {
            "summary" => package_summary.sort.to_h,
            "selected" => selected_packages,
            "all" => enriched_packages
          },
          "paths" => paths
        }
      end

      def self.delete!(instance_name)
        path = Workdir.state_path(instance_name)
        lp = lock_path(instance_name)
        Workdir.ensure_dir(File.dirname(lp))
        File.open(lp, File::RDWR | File::CREAT, 0o600) do |lock|
          lock.flock(File::LOCK_EX)
          File.delete(path) if File.exist?(path)
        end
      end

      def self.history_limit
        DEFAULT_HISTORY_LIMIT
      end

      def self.validate_enum!(value, allowed, label)
        return if allowed.include?(value)

        raise ArgumentError, "#{label} must be one of: #{allowed.join(', ')}"
      end
    end
  end
end
