/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
// icons
import { CloseCircleOutline, HideOutline, ShowOutline } from "@makeplane/propel/icons";
// plane imports
import { Banner } from "@makeplane/propel/components/banner";
import { Input, InputGroup } from "@makeplane/propel/components/input";
import { API_BASE_URL, E_PASSWORD_STRENGTH } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { PasswordStrengthIndicator, Spinner } from "@plane/ui";
import { getPasswordStrength } from "@plane/utils";
// components
import { ForgotPasswordPopover } from "@/components/account/auth-forms/forgot-password-popover";
// constants
// helpers
import { EAuthModes, EAuthSteps } from "@/helpers/authentication.helper";
// services
import { AuthService } from "@/services/auth.service";

type Props = {
  email: string;
  isSMTPConfigured: boolean;
  mode: EAuthModes;
  handleEmailClear: () => void;
  handleAuthStep: (step: EAuthSteps) => void;
  nextPath: string | undefined;
};

type TPasswordFormValues = {
  email: string;
  password: string;
  confirm_password?: string;
};

const defaultValues: TPasswordFormValues = {
  email: "",
  password: "",
};

const authService = new AuthService();

type TAuthPasswordSupportProps = {
  email: string;
  isPasswordInputFocused: boolean;
  isSMTPConfigured: boolean;
  mode: EAuthModes;
  password: string;
};

function AuthPasswordSupport(props: TAuthPasswordSupportProps) {
  const { email, isPasswordInputFocused, isSMTPConfigured, mode, password } = props;
  // plane imports
  const { t } = useTranslation();

  if (mode === EAuthModes.SIGN_IN)
    return (
      <div className="w-full">
        {isSMTPConfigured ? (
          <Link
            href={`/accounts/forgot-password?email=${encodeURIComponent(email)}`}
            className="text-11 font-medium text-accent-primary"
          >
            {t("auth.common.forgot_password")}
          </Link>
        ) : (
          <ForgotPasswordPopover />
        )}
      </div>
    );

  if (password.length === 0 || getPasswordStrength(password) === E_PASSWORD_STRENGTH.STRENGTH_VALID) return null;

  return <PasswordStrengthIndicator password={password} isFocused={isPasswordInputFocused} />;
}

type TAuthConfirmPasswordFieldProps = {
  confirmPassword: string | undefined;
  isInputFocused: boolean;
  isPasswordVisible: boolean;
  password: string;
  onBlur: () => void;
  onChange: (value: string) => void;
  onFocus: () => void;
  onTogglePasswordVisibility: () => void;
};

function AuthConfirmPasswordField(props: TAuthConfirmPasswordFieldProps) {
  const {
    confirmPassword,
    isInputFocused,
    isPasswordVisible,
    password,
    onBlur,
    onChange,
    onFocus,
    onTogglePasswordVisibility,
  } = props;
  // plane imports
  const { t } = useTranslation();
  // derived values
  const renderPasswordMatchError = !isInputFocused || (confirmPassword ?? "").length >= password.length;

  return (
    <div className="space-y-1">
      <label htmlFor="confirm-password" className="text-13 font-medium text-tertiary">
        {t("auth.common.password.confirm_password.label")}
      </label>
      <InputGroup size="2xl">
        <Input
          size="2xl"
          type={isPasswordVisible ? "text" : "password"}
          id="confirm-password"
          name="confirm_password"
          value={confirmPassword}
          onChange={(e) => onChange(e.target.value)}
          placeholder={t("auth.common.password.confirm_password.placeholder")}
          onFocus={onFocus}
          onBlur={onBlur}
          autoComplete="off"
        />
        <button
          type="button"
          className="grid size-5 place-items-center"
          aria-label={t(
            isPasswordVisible ? "aria_labels.auth_forms.hide_password" : "aria_labels.auth_forms.show_password"
          )}
          onClick={onTogglePasswordVisibility}
        >
          {isPasswordVisible ? (
            <HideOutline className="size-5 text-placeholder" />
          ) : (
            <ShowOutline className="size-5 text-placeholder" />
          )}
        </button>
      </InputGroup>
      {!!confirmPassword && password !== confirmPassword && renderPasswordMatchError && (
        <span className="text-13 text-danger-primary">{t("auth.common.password.errors.match")}</span>
      )}
    </div>
  );
}

type TAuthPasswordFormActionsProps = {
  isButtonDisabled: boolean;
  isSMTPConfigured: boolean;
  isSubmitting: boolean;
  mode: EAuthModes;
  onSignInWithUniqueCode: () => void;
};

function AuthPasswordFormActions(props: TAuthPasswordFormActionsProps) {
  const { isButtonDisabled, isSMTPConfigured, isSubmitting, mode, onSignInWithUniqueCode } = props;
  // plane imports
  const { t } = useTranslation();

  return (
    <div className="space-y-2.5">
      {mode === EAuthModes.SIGN_IN ? (
        <>
          <Button type="submit" variant="primary" className="w-full" size="xl" disabled={isButtonDisabled}>
            {isSubmitting ? (
              <Spinner height="20px" width="20px" />
            ) : isSMTPConfigured ? (
              t("common.continue")
            ) : (
              t("common.go_to_workspace")
            )}
          </Button>
          {isSMTPConfigured && (
            <Button type="button" onClick={onSignInWithUniqueCode} variant="secondary" className="w-full" size="xl">
              {t("auth.common.sign_in_with_unique_code")}
            </Button>
          )}
        </>
      ) : (
        <Button type="submit" variant="primary" className="w-full" size="xl" disabled={isButtonDisabled}>
          {isSubmitting ? <Spinner height="20px" width="20px" /> : "Create account"}
        </Button>
      )}
    </div>
  );
}

export const AuthPasswordForm = observer(function AuthPasswordForm(props: Props) {
  const { email, isSMTPConfigured, handleAuthStep, handleEmailClear, mode, nextPath } = props;
  // plane imports
  const { t } = useTranslation();
  // ref
  const formRef = useRef<HTMLFormElement>(null);
  // states
  const [csrfPromise, setCsrfPromise] = useState<Promise<{ csrf_token: string }> | undefined>(undefined);
  const [passwordFormData, setPasswordFormData] = useState<TPasswordFormValues>({ ...defaultValues, email });
  const [showPassword, setShowPassword] = useState({
    password: false,
    retypePassword: false,
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isPasswordInputFocused, setIsPasswordInputFocused] = useState(false);
  const [isRetryPasswordInputFocused, setIsRetryPasswordInputFocused] = useState(false);
  const [isBannerMessage, setBannerMessage] = useState(false);

  const handleShowPassword = (key: keyof typeof showPassword) =>
    setShowPassword((prev) => ({ ...prev, [key]: !prev[key] }));

  const handleFormChange = (key: keyof TPasswordFormValues, value: string) =>
    setPasswordFormData((prev) => ({ ...prev, [key]: value }));

  useEffect(() => {
    if (csrfPromise === undefined) {
      const promise = authService.requestCSRFToken();
      setCsrfPromise(promise);
    }
  }, [csrfPromise]);

  const redirectToUniqueCodeSignIn = async () => {
    handleAuthStep(EAuthSteps.UNIQUE_CODE);
  };

  const isButtonDisabled = useMemo(
    () =>
      !isSubmitting &&
      !!passwordFormData.password &&
      (mode === EAuthModes.SIGN_UP ? passwordFormData.password === passwordFormData.confirm_password : true)
        ? false
        : true,
    [isSubmitting, mode, passwordFormData.confirm_password, passwordFormData.password]
  );

  const handleCSRFToken = async () => {
    if (!formRef || !formRef.current) return;
    const token = await csrfPromise;
    if (!token?.csrf_token) return;
    const csrfElement = formRef.current.querySelector("input[name=csrfmiddlewaretoken]");
    csrfElement?.setAttribute("value", token?.csrf_token);
  };

  return (
    <>
      {isBannerMessage && mode === EAuthModes.SIGN_UP && (
        <Banner
          placement="inline"
          variant="danger"
          description={t("auth.sign_up.errors.password.strength")}
          onDismiss={() => setBannerMessage(false)}
        />
      )}
      <form
        ref={formRef}
        className="space-y-4"
        method="POST"
        action={`${API_BASE_URL}/auth/${mode === EAuthModes.SIGN_IN ? "sign-in" : "sign-up"}/`}
        onSubmit={async (event) => {
          event.preventDefault(); // Prevent form from submitting by default
          await handleCSRFToken();
          const isPasswordValid =
            mode === EAuthModes.SIGN_UP
              ? getPasswordStrength(passwordFormData.password) === E_PASSWORD_STRENGTH.STRENGTH_VALID
              : true;
          if (isPasswordValid) {
            setIsSubmitting(true);
            if (formRef.current) formRef.current.submit(); // Manually submit the form if the condition is met
          } else {
            setBannerMessage(true);
          }
        }}
        onError={() => {
          setIsSubmitting(false);
        }}
      >
        <input type="hidden" name="csrfmiddlewaretoken" />
        <input type="hidden" value={passwordFormData.email} name="email" />
        {nextPath && <input type="hidden" value={nextPath} name="next_path" />}
        <div className="space-y-1">
          <label htmlFor="email" className="text-13 font-medium text-tertiary">
            {t("auth.common.email.label")}
          </label>
          <InputGroup size="2xl">
            <Input
              size="2xl"
              id="email"
              name="email"
              type="email"
              value={passwordFormData.email}
              onChange={(e) => handleFormChange("email", e.target.value)}
              placeholder={t("auth.common.email.placeholder")}
              disabled
            />
            {passwordFormData.email.length > 0 && (
              <button
                type="button"
                className="grid size-5 place-items-center"
                onClick={handleEmailClear}
                aria-label={t("aria_labels.auth_forms.clear_email")}
              >
                <CloseCircleOutline className="size-5 text-placeholder" />
              </button>
            )}
          </InputGroup>
        </div>

        <div className="space-y-1">
          <label htmlFor="password" className="text-13 font-medium text-tertiary">
            {mode === EAuthModes.SIGN_IN ? t("auth.common.password.label") : t("auth.common.password.set_password")}
          </label>
          <InputGroup size="2xl">
            <Input
              size="2xl"
              type={showPassword?.password ? "text" : "password"}
              id="password"
              name="password"
              value={passwordFormData.password}
              onChange={(e) => handleFormChange("password", e.target.value)}
              placeholder={t("auth.common.password.placeholder")}
              onFocus={() => setIsPasswordInputFocused(true)}
              onBlur={() => setIsPasswordInputFocused(false)}
              autoComplete="off"
              autoFocus
            />
            <button
              type="button"
              onClick={() => handleShowPassword("password")}
              className="grid size-5 place-items-center"
              aria-label={t(
                showPassword?.password ? "aria_labels.auth_forms.hide_password" : "aria_labels.auth_forms.show_password"
              )}
            >
              {showPassword?.password ? (
                <HideOutline className="size-5 text-placeholder" />
              ) : (
                <ShowOutline className="size-5 text-placeholder" />
              )}
            </button>
          </InputGroup>
          <AuthPasswordSupport
            email={email}
            isPasswordInputFocused={isPasswordInputFocused}
            isSMTPConfigured={isSMTPConfigured}
            mode={mode}
            password={passwordFormData.password}
          />
        </div>

        {mode === EAuthModes.SIGN_UP && (
          <AuthConfirmPasswordField
            confirmPassword={passwordFormData.confirm_password}
            isInputFocused={isRetryPasswordInputFocused}
            isPasswordVisible={showPassword.retypePassword}
            password={passwordFormData.password}
            onBlur={() => setIsRetryPasswordInputFocused(false)}
            onChange={(value) => handleFormChange("confirm_password", value)}
            onFocus={() => setIsRetryPasswordInputFocused(true)}
            onTogglePasswordVisibility={() => handleShowPassword("retypePassword")}
          />
        )}

        <AuthPasswordFormActions
          isButtonDisabled={isButtonDisabled}
          isSMTPConfigured={isSMTPConfigured}
          isSubmitting={isSubmitting}
          mode={mode}
          onSignInWithUniqueCode={redirectToUniqueCodeSignIn}
        />
      </form>
    </>
  );
});
