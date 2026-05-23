# frozen_string_literal: true

require "json"

module Eve
  module SDK
    module StateMachine
      VALID_LIVE_STATES = %w[running stopped absent error].freeze

      def self.normalize_provider_state(status)
        normalized = status.to_s.strip.downcase
        case normalized
        when "running", "stopped"
          normalized
        when "not created", "not-created", "absent"
          "absent"
        when "unreachable", "error", "failed"
          "error"
        else
          normalized.empty? ? "unknown" : normalized
        end
      end

      def self.effective_provider_state(state)
        provider_state = state.fetch("provider_state", "unknown").to_s
        desired_state = state.fetch("desired_state", "unknown").to_s
        provision_state = state.fetch("provision_state", "unknown").to_s

        if provider_state == "error" && desired_state == "running" && provision_state == "provisioned"
          "running"
        else
          provider_state
        end
      end

      def self.should_apply_live_provider_state(status, live_state)
        state = status.fetch("state", {})
        return true unless state.is_a?(Hash)

        local_state = effective_provider_state(state)

        return false if live_state == "absent" && local_state == "running"
        return false if live_state == "error" && %w[stopped absent].include?(local_state)

        VALID_LIVE_STATES.include?(live_state)
      end

      def self.status_with_provider_state(status, provider_state)
        result = deep_clone(status)
        state = result["state"]
        if state.nil? && !result.key?("state")
          result["state"] = {}
          state = result["state"]
        elsif !state.is_a?(Hash)
          return result
        end
        state["provider_state"] = provider_state
        if %w[running stopped absent].include?(provider_state) && state.key?("last_error")
          state["last_error"] = nil
        end
        result
      end

      def self.status_with_observed_state(status, state_doc)
        result = deep_clone(status)
        observed = state_doc.fetch("observed_state", {})

        return result unless observed.is_a?(Hash)

        result["observed_state"] = observed

        state = result["state"]
        if state.nil? && !result.key?("state")
          result["state"] = {}
          state = result["state"]
        elsif !state.is_a?(Hash)
          return result
        end

        state["observed_state"] = observed

        provider_status = observed.fetch("provider_status", "").to_s
        provider_state = provider_status == "unreachable" ? "error" : provider_status

        if !provider_state.empty? && should_apply_live_provider_state(result, provider_state)
          result = status_with_provider_state(result, provider_state)
        end

        result
      end

      def self.provider_actions_available(state)
        eps = effective_provider_state(state)
        desired_state = state.fetch("desired_state", "unknown").to_s
        provision_state = state.fetch("provision_state", "unknown").to_s
        eps == "running" || (eps == "error" && desired_state == "running" && provision_state == "provisioned")
      end

      def self.aggregate_summary(statuses)
        counts = { "running" => 0, "stopped" => 0, "failed" => 0, "other" => 0 }
        statuses.each do |_name, status|
          state = status.fetch("state", {})
          provider_state = state.fetch("provider_state", "unknown").to_s
          last_error = state["last_error"]
          if last_error || %w[failed error].include?(provider_state)
            counts["failed"] += 1
          elsif provider_state == "running"
            counts["running"] += 1
          elsif %w[stopped absent].include?(provider_state)
            counts["stopped"] += 1
          else
            counts["other"] += 1
          end
        end
        counts
      end

      def self.deep_clone(obj)
        JSON.parse(JSON.generate(obj))
      end
      private_class_method :deep_clone
    end
  end
end
