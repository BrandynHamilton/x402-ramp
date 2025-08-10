import axios from "axios";
import type { AxiosInstance } from "axios";

import pkg from "@stellar/typescript-wallet-sdk";
const { Wallet, StellarConfiguration, ApplicationConfiguration, DefaultSigner, Keypair, TransactionBuilder, SigningKeypair, IssuedAssetId } = pkg;

const pk = process.env.THIRD_PARTY_STELLAR_KEY;
if (!pk) {
  throw new Error("THIRD_PARTY_STELLAR_KEY is not set in environment variables");
}
const authKey = SigningKeypair.fromSecret(pk);

const customClient: AxiosInstance = axios.create({
  timeout: 1000,
});

const appConfig = new ApplicationConfiguration(DefaultSigner, customClient);

const wallet = new Wallet({
  stellarConfiguration: StellarConfiguration.TestNet(),
  applicationConfiguration: appConfig,
});

let account = wallet.stellar().account();
let accountKeyPair = account.createKeypair();

let anchor = wallet.anchor({ homeDomain: "localhost:8080", allowHttp: true });

let resp = await anchor.sep1();
console.log("SEP-1 Response:", resp);

const sep10 = await anchor.sep10();
const authToken = await sep10.authenticate({ accountKp: authKey });

const sep24 = await anchor.sep24();



const assetCode = "USDC";

const info = await anchor.getInfo();
const services = await anchor.getServicesInfo();
console.log("Anchor Info:", info);
console.log("Anchor Services:", services);

const currency = info.currencies.find(({ code }) => code === assetCode);

if (!currency?.code || !currency?.issuer) {
  throw new Error(
    `Anchor does not support ${assetCode} asset or is not correctly configured on TOML file`,
  );
}

const asset = new IssuedAssetId(currency.code, currency.issuer);

try {
  const withdrawal = await sep24.withdraw({
    assetCode: asset.code,
    authToken,
  });
  const url = withdrawal.url;
  const id = withdrawal.id;

  console.log("Withdrawal URL:", url);
  console.log("Withdrawal ID:", id);
} catch (err: any) {
  console.error("Withdrawal request failed");
  if (err.response) {
    console.error("Status:", err.response.status);
    console.error("Data:", err.response.data);
  } else if (err.request) {
    console.error("No response received");
  } else {
    console.error("Error:", err.message);
  }
}
