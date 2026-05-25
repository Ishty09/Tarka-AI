import {
  Body,
  Container,
  Head,
  Heading,
  Html,
  Link,
  Preview,
  Section,
  Text,
} from "@react-email/components";

interface WelcomeEmailProps {
  display_name: string;
  app_url: string;
}

export default function WelcomeEmail({
  display_name = "there",
  app_url = "https://quarrel.ai",
}: WelcomeEmailProps) {
  return (
    <Html lang="en">
      <Head />
      <Preview>You signed up for the AI that won&apos;t agree with you. Now what.</Preview>
      <Body style={{ fontFamily: "system-ui, sans-serif", background: "#ffffff" }}>
        <Container style={{ margin: "0 auto", padding: "24px", maxWidth: "560px" }}>
          <Heading style={{ fontSize: "24px", fontWeight: 600, marginBottom: "16px" }}>
            Welcome to Quarrel, {display_name}.
          </Heading>
          <Section>
            <Text style={{ fontSize: "16px", lineHeight: "24px", color: "#111" }}>
              You picked the AI that pushes back. That&apos;s the deal — every chat,
              every roast, every wager. We&apos;ll remember what you said two weeks
              ago and bring it up when you contradict yourself.
            </Text>
            <Text style={{ fontSize: "16px", lineHeight: "24px", color: "#111" }}>
              Three things to do first:
            </Text>
            <Text style={{ fontSize: "16px", lineHeight: "24px", color: "#111", margin: "8px 0" }}>
              1. Pick a persona →{" "}
              <Link href={`${app_url}/personas`} style={{ color: "#000" }}>
                {app_url}/personas
              </Link>
            </Text>
            <Text style={{ fontSize: "16px", lineHeight: "24px", color: "#111", margin: "8px 0" }}>
              2. Throw something at it you&apos;d normally ask ChatGPT.
              See the difference.
            </Text>
            <Text style={{ fontSize: "16px", lineHeight: "24px", color: "#111", margin: "8px 0" }}>
              3. When you contradict yourself, it&apos;ll call you out. That&apos;s
              the point.
            </Text>
          </Section>
          <Section style={{ borderTop: "1px solid #eee", marginTop: "32px", paddingTop: "16px" }}>
            <Text style={{ fontSize: "12px", color: "#666" }}>
              You can manage notifications, change persona defaults, or close
              your account at any time in{" "}
              <Link href={`${app_url}/settings`} style={{ color: "#666" }}>
                Settings
              </Link>
              . Quarrel AI — Dhaka, Bangladesh.
            </Text>
          </Section>
        </Container>
      </Body>
    </Html>
  );
}
