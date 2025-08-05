import { AllbridgeCoreSdk, nodeRpcUrlsDefault, ChainSymbol } from "@allbridge/bridge-core-sdk";

const sdk = new AllbridgeCoreSdk(nodeRpcUrlsDefault);

async function main() {
  const chains = await sdk.chainDetailsMap();
  console.log("Chain details map =", JSON.stringify(chains, null, 2));

  const tokens = await sdk.tokens();
  console.log("Tokens =", JSON.stringify(tokens, null, 2));

  const sourceChain = chains[ChainSymbol.SRB];
  const destinationChain = chains[ChainSymbol.POL];

  if (!sourceChain) {
    throw new Error("Source chain STLR not found.");
  }

  if (!destinationChain) {
    throw new Error("Destination chain POL not found.");
  }

  const sourceTokenInfo = sourceChain.tokens.find((tokenInfo) => tokenInfo.symbol === "USDC");
  const destinationTokenInfo = destinationChain.tokens.find((tokenInfo) => tokenInfo.symbol === "USDC");

  if (!sourceTokenInfo || !destinationTokenInfo) {
    throw new Error("USDC token not found on one or both chains.");
  }

  console.log("Source Token Info:", sourceTokenInfo);
  console.log("Destination Token Info:", destinationTokenInfo);
}

main().catch(console.error);
