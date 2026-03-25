import React from "react";
import { Text as RNText, TextProps } from "react-native";
import { theme } from "../../theme";

type Variant = "display" | "headline" | "body" | "label";

type Props = TextProps & {
  variant?: Variant;
  color?: string;
  uppercase?: boolean;
};

export function Text({ variant = "body", color, style, uppercase, children, ...rest }: Props) {
  const variantStyle = theme.typography[variant];
  return (
    <RNText
      {...rest}
      style={[
        variantStyle,
        { color: color ?? theme.colors.onSurface },
        uppercase ? { textTransform: "uppercase" } : null,
        style,
      ]}
    >
      {children}
    </RNText>
  );
}
