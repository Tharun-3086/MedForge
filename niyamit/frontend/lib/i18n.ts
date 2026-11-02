// Patient and caregiver screens in English, Hindi and Telugu. Staff screens are English.
// Wording is draft copy for the synthetic demo; it should be reviewed by native speakers and the clinic.

export type Lang = "en" | "hi" | "te";
export const LANGS: { code: Lang; label: string }[] = [
  { code: "te", label: "తెలుగు" },
  { code: "hi", label: "हिन्दी" },
  { code: "en", label: "English" },
];

type Dict = Record<string, { en: string; hi: string; te: string }>;

const S: Dict = {
  loading: { en: "Loading…", hi: "लोड हो रहा है…", te: "లోడ్ అవుతోంది…" },
  verifyTitle: { en: "Confirm it is you", hi: "पुष्टि करें कि यह आप हैं", te: "ఇది మీరేనని నిర్ధారించండి" },
  verifyHelp: {
    en: "Enter your year of birth to see your follow-up details.",
    hi: "अपनी फॉलो-अप जानकारी देखने के लिए अपना जन्म वर्ष लिखें।",
    te: "మీ ఫాలో-అప్ వివరాలు చూడటానికి మీ పుట్టిన సంవత్సరం నమోదు చేయండి.",
  },
  birthYear: { en: "Year of birth", hi: "जन्म वर्ष", te: "పుట్టిన సంవత్సరం" },
  continue: { en: "Continue", hi: "आगे बढ़ें", te: "కొనసాగించండి" },
  linkProblem: {
    en: "This link does not work any more. Ask the clinic to send a new one.",
    hi: "यह लिंक अब काम नहीं करता। क्लिनिक से नया लिंक भेजने को कहें।",
    te: "ఈ లింక్ ఇక పని చేయదు. కొత్త లింక్ పంపమని క్లినిక్‌ను అడగండి.",
  },
  hello: { en: "Namaste, {name}", hi: "नमस्ते, {name}", te: "నమస్తే, {name}" },
  nextFollowUp: { en: "Your next follow-up", hi: "आपका अगला फॉलो-अप", te: "మీ తదుపరి ఫాలో-అప్" },
  alsoDue: { en: "Also due", hi: "यह भी बाकी है", te: "ఇవి కూడా ఉన్నాయి" },
  noFollowUp: { en: "No follow-up is due right now.", hi: "अभी कोई फॉलो-अप बाकी नहीं है।", te: "ప్రస్తుతం ఫాలో-అప్ ఏదీ లేదు." },
  overdueBy: { en: "{n} days late", hi: "{n} दिन देर", te: "{n} రోజులు ఆలస్యం" },
  overdueByOne: { en: "1 day late", hi: "1 दिन देर", te: "1 రోజు ఆలస్యం" },
  dueToday: { en: "Today", hi: "आज", te: "ఈరోజు" },
  dueTomorrow: { en: "Tomorrow", hi: "कल", te: "రేపు" },
  dueInDays: { en: "In {n} days", hi: "{n} दिन में", te: "{n} రోజుల్లో" },
  confirm: { en: "I will come", hi: "मैं आऊँगा / आऊँगी", te: "నేను వస్తాను" },
  reschedule: { en: "Change the date", hi: "तारीख बदलें", te: "తేదీ మార్చండి" },
  problem: { en: "I have a problem coming", hi: "आने में दिक्कत है", te: "రావడంలో ఇబ్బంది ఉంది" },
  callMe: { en: "Please call me", hi: "मुझे कॉल करें", te: "నాకు కాల్ చేయండి" },
  ownWords: { en: "Or tell us in your own words", hi: "या अपने शब्दों में बताएं", te: "లేదా మీ మాటల్లో చెప్పండి" },
  typeHere: { en: "Type your message", hi: "अपना संदेश लिखें", te: "మీ సందేశం టైప్ చేయండి" },
  send: { en: "Send", hi: "भेजें", te: "పంపండి" },
  record: { en: "Record a voice message", hi: "आवाज़ में संदेश रिकॉर्ड करें", te: "వాయిస్ సందేశం రికార్డ్ చేయండి" },
  stopSend: { en: "Stop and send ({s})", hi: "रोकें और भेजें ({s})", te: "ఆపి పంపండి ({s})" },
  voiceOff: {
    en: "Voice messages are not available right now. Please type, or use the buttons above.",
    hi: "अभी वॉइस संदेश उपलब्ध नहीं है। कृपया लिखें, या ऊपर के बटन चुनें।",
    te: "ప్రస్తుతం వాయిస్ సందేశాలు అందుబాటులో లేవు. దయచేసి టైప్ చేయండి, లేదా పై బటన్లు వాడండి.",
  },
  micBlocked: {
    en: "The microphone is blocked. Please type instead.",
    hi: "माइक्रोफ़ोन बंद है। कृपया लिखकर भेजें।",
    te: "మైక్రోఫోన్‌కు అనుమతి లేదు. దయచేసి టైప్ చేయండి.",
  },
  aiConsentTitle: { en: "Allow voice messages?", hi: "वॉइस संदेशों की अनुमति दें?", te: "వాయిస్ సందేశాలకు అనుమతి ఇవ్వాలా?" },
  aiConsentBody: {
    en: "To understand voice messages, your recording is sent to Sarvam AI (India), which turns speech into text. The clinic team sees the text. You can always type or use the buttons instead.",
    hi: "वॉइस संदेश समझने के लिए आपकी रिकॉर्डिंग Sarvam AI (भारत) को भेजी जाती है, जो आवाज़ को लिखित में बदलता है। क्लिनिक टीम वह लिखित संदेश देखती है। आप हमेशा लिखकर या बटन से भी जवाब दे सकते हैं।",
    te: "వాయిస్ సందేశాలను అర్థం చేసుకోవడానికి, మీ రికార్డింగ్‌ను Sarvam AI (భారతదేశం)కు పంపుతాము, అది మాటలను అక్షరాలుగా మారుస్తుంది. క్లినిక్ బృందం ఆ అక్షరాలను చూస్తుంది. మీరు ఎప్పుడైనా టైప్ చేయవచ్చు లేదా బటన్లు వాడవచ్చు.",
  },
  allow: { en: "Allow", hi: "अनुमति दें", te: "అనుమతించండి" },
  notNow: { en: "Not now", hi: "अभी नहीं", te: "ఇప్పుడు కాదు" },
  understood: { en: "What we understood", hi: "हमने क्या समझा", te: "మేము అర్థం చేసుకున్నది" },
  youSaid: { en: "You said", hi: "आपने कहा", te: "మీరు చెప్పింది" },
  weHeard: { en: "We heard", hi: "हमने सुना", te: "మేము విన్నది" },
  working: { en: "Reading your message…", hi: "आपका संदेश पढ़ा जा रहा है…", te: "మీ సందేశాన్ని చదువుతున్నాం…" },
  correct: { en: "Not right? Correct it", hi: "सही नहीं? ठीक करें", te: "సరిగా లేదా? సరిచేయండి" },
  correctHelp: { en: "Type what you meant", hi: "आप जो कहना चाहते थे वह लिखें", te: "మీరు చెప్పాలనుకున్నది టైప్ చేయండి" },
  saveCorrection: { en: "Send correction", hi: "सुधार भेजें", te: "సవరణ పంపండి" },
  voiceFailed: {
    en: "We could not understand the recording. Please type your message, or use the buttons.",
    hi: "हम रिकॉर्डिंग समझ नहीं पाए। कृपया अपना संदेश लिखें, या बटन चुनें।",
    te: "రికార్డింగ్ అర్థం కాలేదు. దయచేసి మీ సందేశం టైప్ చేయండి, లేదా బటన్లు వాడండి.",
  },
  voiceNeedsConsent: {
    en: "Voice messages need your permission first. You can type instead.",
    hi: "वॉइस संदेश के लिए पहले आपकी अनुमति चाहिए। आप लिखकर भी भेज सकते हैं।",
    te: "వాయిస్ సందేశాలకు ముందుగా మీ అనుమతి కావాలి. మీరు టైప్ చేసి కూడా పంపవచ్చు.",
  },
  pickTime: { en: "Pick a time", hi: "समय चुनें", te: "సమయం ఎంచుకోండి" },
  whichOfTwoDays: {
    en: "Which day do you mean: {a} or {b}? Pick a time on that day.",
    hi: "आपका मतलब कौन सा दिन है: {a} या {b}? उसी दिन का कोई समय चुनें।",
    te: "మీరు అన్నది ఏ రోజు: {a} లేదా {b}? ఆ రోజులో ఒక సమయం ఎంచుకోండి.",
  },
  pickDay: { en: "Which day suits you? Pick a time below.", hi: "कौन सा दिन ठीक रहेगा? नीचे समय चुनें।", te: "ఏ రోజు మీకు వీలవుతుంది? కింద సమయం ఎంచుకోండి." },
  confirmDay: { en: "You asked for {day}. Pick a time on {date} to book it.", hi: "आपने {day} कहा। बुक करने के लिए {date} का समय चुनें।", te: "మీరు {day} అన్నారు. బుక్ చేయడానికి {date} న సమయం ఎంచుకోండి." },
  noSlotsDay: { en: "No open times on {date}. These are the next free times.", hi: "{date} को कोई समय खाली नहीं है। ये अगले खाली समय हैं।", te: "{date} న ఖాళీ సమయాలు లేవు. తదుపరి ఖాళీ సమయాలు ఇవి." },
  mismatch: {
    en: "Your follow-up is on {due}. You mentioned “{day}”. Keep {due}, or change the date?",
    hi: "आपका फॉलो-अप {due} को है। आपने “{day}” कहा। {due} रखें या तारीख बदलें?",
    te: "మీ ఫాలో-అప్ {due} న ఉంది. మీరు “{day}” అన్నారు. {due} నే ఉంచాలా, లేక తేదీ మార్చాలా?",
  },
  keepDate: { en: "Keep {due}", hi: "{due} रखें", te: "{due} నే ఉంచండి" },
  clarify: { en: "Sorry, we are not sure what you need. Please choose one:", hi: "माफ़ कीजिए, हम समझ नहीं पाए आपको क्या चाहिए। कृपया एक चुनें:", te: "క్షమించండి, మీకు ఏమి కావాలో మాకు స్పష్టంగా తెలియలేదు. దయచేసి ఒకటి ఎంచుకోండి:" },
  optOutQuestion: { en: "Stop all reminder messages from the clinic?", hi: "क्लिनिक के सभी रिमाइंडर संदेश बंद करें?", te: "క్లినిక్ నుండి వచ్చే అన్ని రిమైండర్ సందేశాలు ఆపాలా?" },
  yesStop: { en: "Yes, stop them", hi: "हाँ, बंद करें", te: "అవును, ఆపండి" },
  noKeep: { en: "No, keep them", hi: "नहीं, जारी रखें", te: "వద్దు, కొనసాగించండి" },
  book: { en: "Book {time}", hi: "{time} बुक करें", te: "{time} బుక్ చేయండి" },
  booked: { en: "Booked: {time}. Reference {ref}.", hi: "बुक हो गया: {time}। संदर्भ {ref}।", te: "బుక్ అయింది: {time}. రిఫరెన్స్ {ref}." },
  bookedRef: { en: "Booked. Reference {ref}.", hi: "बुक हो गया। संदर्भ {ref}।", te: "బుక్ అయింది. రిఫరెన్స్ {ref}." },
  notBooked: { en: "Not booked. The clinic will call you to fix a time.", hi: "बुक नहीं हुआ। समय तय करने के लिए क्लिनिक आपको कॉल करेगा।", te: "బుక్ కాలేదు. సమయం నిర్ణయించడానికి క్లినిక్ మీకు కాల్ చేస్తుంది." },
  slotTaken: { en: "That time was just taken. Please pick another.", hi: "यह समय अभी-अभी किसी और ने ले लिया। कृपया दूसरा चुनें।", te: "ఆ సమయం ఇప్పుడే వేరొకరికి బుక్ అయింది. దయచేసి మరొకటి ఎంచుకోండి." },
  noSlots: { en: "No open times right now. Ask for a call instead.", hi: "अभी कोई समय खाली नहीं है। इसके बजाय कॉल के लिए कहें।", te: "ప్రస్తుతం ఖాళీ సమయాలు లేవు. బదులుగా కాల్ కోసం అడగండి." },
  bookingDown: { en: "Booking is not available right now. Ask for a call instead.", hi: "अभी बुकिंग उपलब्ध नहीं है। इसके बजाय कॉल के लिए कहें।", te: "ప్రస్తుతం బుకింగ్ అందుబాటులో లేదు. బదులుగా కాల్ కోసం అడగండి." },
  barrierTitle: { en: "What makes it hard to come?", hi: "आने में क्या दिक्कत है?", te: "రావడానికి ఏమి ఇబ్బంది?" },
  barrierHelp: { en: "A clinic team member will contact you about it.", hi: "क्लिनिक टीम का कोई सदस्य इस बारे में आपसे संपर्क करेगा।", te: "దీని గురించి క్లినిక్ బృందం నుండి ఒకరు మిమ్మల్ని సంప్రదిస్తారు." },
  shareReport: { en: "Share a report", hi: "रिपोर्ट भेजें", te: "రిపోర్ట్ పంపండి" },
  shareReportHelp: { en: "Photo or PDF of a lab report or prescription.", hi: "लैब रिपोर्ट या पर्चे की फोटो या PDF।", te: "ల్యాబ్ రిపోర్ట్ లేదా ప్రిస్క్రిప్షన్ ఫోటో లేదా PDF." },
  chooseFile: { en: "Choose a photo or PDF", hi: "फोटो या PDF चुनें", te: "ఫోటో లేదా PDF ఎంచుకోండి" },
  uploading: { en: "Sending…", hi: "भेजा जा रहा है…", te: "పంపుతున్నాం…" },
  reportReceived: { en: "Received. The clinic team will look at it.", hi: "मिल गया। क्लिनिक टीम इसे देखेगी।", te: "అందింది. క్లినిక్ బృందం దాన్ని చూస్తుంది." },
  passport: { en: "My care record", hi: "मेरा देखभाल रिकॉर्ड", te: "నా సంరక్షణ రికార్డు" },
  family: { en: "Family access", hi: "परिवार की पहुँच", te: "కుటుంబ సభ్యుల యాక్సెస్" },
  back: { en: "Back", hi: "वापस", te: "వెనక్కి" },
  listen: { en: "Listen", hi: "सुनें", te: "వినండి" },
  callClinic: { en: "Call the clinic: {phone}", hi: "क्लिनिक को कॉल करें: {phone}", te: "క్లినిక్‌కు కాల్ చేయండి: {phone}" },
  emergency: { en: "In an emergency, call 108 or 112.", hi: "आपातकाल में 108 या 112 पर कॉल करें।", te: "అత్యవసర పరిస్థితిలో 108 లేదా 112కు కాల్ చేయండి." },
  appointments: { en: "Booked appointments", hi: "बुक की गई मुलाकातें", te: "బుక్ చేసిన అపాయింట్‌మెంట్‌లు" },
  ref: { en: "Ref {ref}", hi: "संदर्भ {ref}", te: "రిఫరెన్స్ {ref}" },
  planTitle: { en: "Your follow-up plan", hi: "आपकी फॉलो-अप योजना", te: "మీ ఫాలో-అప్ ప్లాన్" },
  planApproved: { en: "Approved by the clinic on {date}", hi: "क्लिनिक ने {date} को स्वीकृत किया", te: "క్లినిక్ {date} న ఆమోదించింది" },
  requests: { en: "Your requests", hi: "आपके अनुरोध", te: "మీ అభ్యర్థనలు" },
  toldUs: { en: "What you told us", hi: "आपने हमें क्या बताया", te: "మీరు మాకు చెప్పినవి" },
  workingOnIt: { en: "The clinic is working on it", hi: "क्लिनिक इस पर काम कर रहा है", te: "క్లినిక్ దీనిపై పని చేస్తోంది" },
  closed: { en: "Closed", hi: "पूरा हुआ", te: "పూర్తయింది" },
  documents: { en: "Reports you shared", hi: "आपकी भेजी रिपोर्ट", te: "మీరు పంపిన రిపోర్ట్‌లు" },
  messages: { en: "Messages from the clinic", hi: "क्लिनिक के संदेश", te: "క్లినిక్ సందేశాలు" },
  reminders: { en: "Reminder messages", hi: "रिमाइंडर संदेश", te: "రిమైండర్ సందేశాలు" },
  remindersOn: { en: "You get reminders.", hi: "आपको रिमाइंडर मिलते हैं।", te: "మీకు రిమైండర్లు వస్తాయి." },
  remindersOff: { en: "You asked us to stop reminders.", hi: "आपने रिमाइंडर बंद करने को कहा है।", te: "రిమైండర్లు ఆపమని మీరు అడిగారు." },
  stopReminders: { en: "Stop reminders", hi: "रिमाइंडर बंद करें", te: "రిమైండర్లు ఆపండి" },
  startReminders: { en: "Start reminders again", hi: "रिमाइंडर फिर शुरू करें", te: "రిమైండర్లు మళ్ళీ ప్రారంభించండి" },
  nothingYet: { en: "Nothing here yet.", hi: "अभी यहाँ कुछ नहीं है।", te: "ఇక్కడ ఇంకా ఏమీ లేదు." },
  familyHelp: {
    en: "Give a family member limited access. They can only do what you tick, and you can remove it at any time.",
    hi: "परिवार के किसी सदस्य को सीमित पहुँच दें। वे केवल वही कर सकते हैं जो आप चुनें, और आप इसे कभी भी हटा सकते हैं।",
    te: "కుటుంబ సభ్యులకు పరిమిత యాక్సెస్ ఇవ్వండి. మీరు ఎంచుకున్నవి మాత్రమే వారు చేయగలరు, మీరు ఎప్పుడైనా తొలగించవచ్చు.",
  },
  theirName: { en: "Their name", hi: "उनका नाम", te: "వారి పేరు" },
  theirPhone: { en: "Their mobile number", hi: "उनका मोबाइल नंबर", te: "వారి మొబైల్ నంబర్" },
  giveAccess: { en: "Give access", hi: "पहुँच दें", te: "యాక్సెస్ ఇవ్వండి" },
  shareLink: { en: "Send this link to them yourself:", hi: "यह लिंक उन्हें खुद भेजें:", te: "ఈ లింక్‌ను మీరే వారికి పంపండి:" },
  copyLink: { en: "Copy link", hi: "लिंक कॉपी करें", te: "లింక్ కాపీ చేయండి" },
  copied: { en: "Copied", hi: "कॉपी हो गया", te: "కాపీ అయింది" },
  removeAccess: { en: "Remove access", hi: "पहुँच हटाएं", te: "యాక్సెస్ తొలగించండి" },
  removed: { en: "Access removed", hi: "पहुँच हटा दी गई", te: "యాక్సెస్ తొలగించారు" },
  scope_VIEW_APPOINTMENTS: { en: "See follow-ups and appointments", hi: "फॉलो-अप और मुलाकातें देख सकें", te: "ఫాలో-అప్‌లు, అపాయింట్‌మెంట్‌లు చూడగలరు" },
  scope_REQUEST_RESCHEDULE: { en: "Ask for a new appointment time", hi: "नए समय का अनुरोध कर सकें", te: "కొత్త సమయం కోసం అడగగలరు" },
  scope_RECEIVE_REMINDER_COPY: { en: "Get a copy of reminders", hi: "रिमाइंडर की कॉपी पाएं", te: "రిమైండర్ల కాపీ పొందగలరు" },
  caregiverHello: { en: "Namaste, {name}", hi: "नमस्ते, {name}", te: "నమస్తే, {name}" },
  caregiverFor: { en: "You are helping {name} with follow-ups at {clinic}.", hi: "आप {clinic} में {name} के फॉलो-अप में मदद कर रहे हैं।", te: "మీరు {clinic}లో {name} గారి ఫాలో-అప్‌లలో సహాయం చేస్తున్నారు." },
  caregiverAsk: { en: "Ask for a new time", hi: "नए समय के लिए कहें", te: "కొత్త సమయం అడగండి" },
  whichDay: { en: "Which day? (for example: Saturday, tomorrow, 12 tareekh)", hi: "कौन सा दिन? (जैसे: शनिवार, कल, 12 तारीख)", te: "ఏ రోజు? (ఉదా: శనివారం, రేపు, 12 తేదీ)" },
  morning: { en: "Morning", hi: "सुबह", te: "ఉదయం" },
  afternoon: { en: "Afternoon", hi: "दोपहर", te: "మధ్యాహ్నం" },
  evening: { en: "Evening", hi: "शाम", te: "సాయంత్రం" },
  anyTime: { en: "Any time", hi: "कोई भी समय", te: "ఏ సమయమైనా" },
  showTimes: { en: "Show free times", hi: "खाली समय दिखाएं", te: "ఖాళీ సమయాలు చూపండి" },
  signOut: { en: "Sign out", hi: "बाहर निकलें", te: "సైన్ అవుట్" },
  revokedAccess: { en: "This access was removed by the patient, or it has expired.", hi: "यह पहुँच मरीज़ ने हटा दी है, या इसकी समय-सीमा खत्म हो गई है।", te: "ఈ యాక్సెస్‌ను రోగి తొలగించారు, లేదా దాని గడువు ముగిసింది." },
  demoNote: { en: "Demo with made-up patient data.", hi: "बनावटी मरीज़ डेटा वाला डेमो।", te: "కల్పిత రోగి సమాచారంతో డెమో." },
};

// What the patient is told about each part of their message.
const INTENT: Dict = {
  CONFIRM_FOLLOWUP: { en: "Confirm your follow-up", hi: "फॉलो-अप की पुष्टि", te: "ఫాలో-అప్ నిర్ధారణ" },
  RESCHEDULE_REQUEST: { en: "Change the date or time", hi: "तारीख या समय बदलना", te: "తేదీ లేదా సమయం మార్పు" },
  REPORT_UPLOAD_INTENT: { en: "Share a report", hi: "रिपोर्ट भेजना", te: "రిపోర్ట్ పంపడం" },
  CALLBACK_REQUEST: { en: "A call from the clinic", hi: "क्लिनिक से कॉल", te: "క్లినిక్ నుండి కాల్" },
  BARRIER_REPORTED: { en: "A difficulty in coming", hi: "आने में दिक्कत", te: "రావడంలో ఇబ్బంది" },
  CLINICAL_QUESTION: { en: "A question for the clinic", hi: "क्लिनिक के लिए सवाल", te: "క్లినిక్‌కు ప్రశ్న" },
  URGENT_CONCERN: { en: "A possible urgent problem", hi: "संभावित गंभीर समस्या", te: "అత్యవసర సమస్య కావచ్చు" },
  OPT_OUT: { en: "Stop reminder messages", hi: "रिमाइंडर संदेश बंद करना", te: "రిమైండర్ సందేశాలు ఆపడం" },
  OTHER_OR_UNCLEAR: { en: "Not clear yet", hi: "अभी स्पष्ट नहीं", te: "ఇంకా స్పష్టంగా లేదు" },
};

const ACTION_STATUS: Dict = {
  DONE: { en: "Done", hi: "हो गया", te: "పూర్తయింది" },
  BOOKED: { en: "Booked", hi: "बुक हो गया", te: "బుక్ అయింది" },
  HANDED_TO_CLINICIAN: { en: "Sent to the clinic nurse", hi: "क्लिनिक नर्स को भेजा गया", te: "క్లినిక్ నర్సుకు పంపాము" },
  HANDED_TO_STAFF: { en: "The clinic team will contact you", hi: "क्लिनिक टीम आपसे संपर्क करेगी", te: "క్లినిక్ బృందం మిమ్మల్ని సంప్రదిస్తుంది" },
  AWAITING_SLOT_CHOICE: { en: "Waiting for your choice", hi: "आपके चुनाव का इंतज़ार", te: "మీ ఎంపిక కోసం వేచి ఉంది" },
  AWAITING_CONFIRMATION: { en: "Please confirm", hi: "कृपया पुष्टि करें", te: "దయచేసి నిర్ధారించండి" },
  AWAITING_CLARIFICATION: { en: "Please choose one", hi: "कृपया एक चुनें", te: "దయచేసి ఒకటి ఎంచుకోండి" },
  AWAITING_UPLOAD: { en: "Add the report below", hi: "नीचे रिपोर्ट जोड़ें", te: "కింద రిపోర్ట్ జోడించండి" },
  NO_OPEN_FOLLOW_UP: { en: "No follow-up is due", hi: "कोई फॉलो-अप बाकी नहीं", te: "ఫాలో-అప్ ఏదీ లేదు" },
  ALREADY_RECORDED: { en: "Already noted. Thank you.", hi: "पहले ही दर्ज है। धन्यवाद।", te: "ఇప్పటికే నమోదైంది. ధన్యవాదాలు." },
  SUPERSEDED: { en: "Replaced by your correction", hi: "आपके सुधार से बदल दिया गया", te: "మీ సవరణతో మార్చాము" },
  DECLINED: { en: "Kept as before", hi: "पहले जैसा रखा गया", te: "ముందులాగే ఉంచాము" },
};

const BARRIER: Dict = {
  TIMING: { en: "The time does not suit me", hi: "यह समय मेरे लिए ठीक नहीं", te: "ఈ సమయం నాకు వీలు కాదు" },
  TRANSPORT: { en: "Travel or transport", hi: "आने-जाने की दिक्कत", te: "ప్రయాణం లేదా వాహనం ఇబ్బంది" },
  COST: { en: "Cost", hi: "खर्च", te: "ఖర్చు" },
  CONFUSION: { en: "I am not sure what to do", hi: "समझ नहीं आ रहा क्या करना है", te: "ఏమి చేయాలో అర్థం కావడం లేదు" },
  FEELING_WELL: { en: "I feel fine, so I don't need to come", hi: "मैं ठीक हूँ, आने की ज़रूरत नहीं लगती", te: "నేను బాగానే ఉన్నాను, రావాల్సిన అవసరం లేదనిపిస్తోంది" },
  CAREGIVER_LOGISTICS: { en: "No one to come with me", hi: "साथ आने वाला कोई नहीं", te: "నాతో రావడానికి ఎవరూ లేరు" },
  OTHER: { en: "Something else", hi: "कुछ और", te: "ఇంకేదైనా" },
  PREFER_NOT_TO_SAY: { en: "I would rather not say", hi: "मैं नहीं बताना चाहता / चाहती", te: "నేను చెప్పదలచుకోలేదు" },
};

const ITEM_STATUS: Dict = {
  PENDING: { en: "Coming up", hi: "आने वाला", te: "ఇంకా జరగాలి" },
  CONFIRMED_BY_PATIENT: { en: "You confirmed", hi: "आपने पुष्टि की", te: "మీరు నిర్ధారించారు" },
  BOOKED: { en: "Booked", hi: "बुक है", te: "బుక్ అయింది" },
  COMPLETED: { en: "Done", hi: "पूरा", te: "పూర్తయింది" },
};

const ITEM_KIND: Dict = {
  REVIEW_VISIT: { en: "Review visit", hi: "जाँच के लिए मुलाकात", te: "రివ్యూ విజిట్" },
  HBA1C_TEST: { en: "HbA1c test", hi: "HbA1c जाँच", te: "HbA1c పరీక్ష" },
  EYE_EXAM: { en: "Eye (retina) check", hi: "आँखों (रेटिना) की जाँच", te: "కంటి (రెటీనా) పరీక్ష" },
  FOOT_EXAM: { en: "Foot check", hi: "पैरों की जाँच", te: "పాదాల పరీక్ష" },
  KIDNEY_TEST: { en: "Kidney test", hi: "किडनी की जाँच", te: "కిడ్నీ పరీక్ష" },
  MEDICINE_REFILL: { en: "Medicine refill", hi: "दवा दोबारा लेना", te: "మందులు మళ్ళీ తీసుకోవడం" },
  OTHER: { en: "Follow-up", hi: "फॉलो-अप", te: "ఫాలో-అప్" },
};

const REQUEST_STATUS: Dict = {
  REQUESTED: { en: "Request received", hi: "अनुरोध मिला", te: "అభ్యర్థన అందింది" },
  NEEDS_CLARIFICATION: { en: "Waiting for your day choice", hi: "आपके दिन के चुनाव का इंतज़ार", te: "మీరు రోజు ఎంచుకోవాలి" },
  SLOTS_OFFERED: { en: "Waiting for your time choice", hi: "आपके समय के चुनाव का इंतज़ार", te: "మీరు సమయం ఎంచుకోవాలి" },
  BOOKED: { en: "Booked", hi: "बुक हो गया", te: "బుక్ అయింది" },
  NOT_BOOKED: { en: "Not booked", hi: "बुक नहीं हुआ", te: "బుక్ కాలేదు" },
  HANDED_TO_STAFF: { en: "Waiting for the clinic (they will call)", hi: "क्लिनिक का इंतज़ार (वे कॉल करेंगे)", te: "క్లినిక్ కోసం వేచి ఉంది (వారు కాల్ చేస్తారు)" },
  CANCELLED: { en: "Cancelled", hi: "रद्द", te: "రద్దయింది" },
};

const MESSAGE_STATUS: Dict = {
  SENT_TO_PROVIDER: { en: "Sent", hi: "भेजा गया", te: "పంపాము" },
  DELIVERED: { en: "Delivered", hi: "पहुँच गया", te: "చేరింది" },
  FAILED: { en: "Not delivered", hi: "नहीं पहुँचा", te: "చేరలేదు" },
  SUPPRESSED: { en: "Not sent", hi: "नहीं भेजा गया", te: "పంపలేదు" },
  UNKNOWN: { en: "Status unknown", hi: "स्थिति पता नहीं", te: "స్థితి తెలియదు" },
  QUEUED: { en: "Sending", hi: "भेजा जा रहा है", te: "పంపుతున్నాం" },
  SENDING: { en: "Sending", hi: "भेजा जा रहा है", te: "పంపుతున్నాం" },
};

function pick(dict: Dict, key: string, lang: Lang): string {
  const entry = dict[key];
  return entry ? entry[lang] || entry.en : key;
}

export function t(lang: Lang, key: string, vars: Record<string, string | number> = {}): string {
  let out = pick(S, key, lang);
  for (const [k, v] of Object.entries(vars)) out = out.split(`{${k}}`).join(String(v));
  return out;
}

export const tIntent = (lang: Lang, key: string) => pick(INTENT, key, lang);
export const tActionStatus = (lang: Lang, key: string) => pick(ACTION_STATUS, key, lang);
export const tBarrier = (lang: Lang, key: string) => pick(BARRIER, key, lang);
export const tItemStatus = (lang: Lang, key: string) => pick(ITEM_STATUS, key, lang);
export const tItemKind = (lang: Lang, key: string) => pick(ITEM_KIND, key, lang);
export const tRequestStatus = (lang: Lang, key: string) => pick(REQUEST_STATUS, key, lang);
export const tMessageStatus = (lang: Lang, key: string) => pick(MESSAGE_STATUS, key, lang);
export const BARRIER_KEYS = Object.keys(BARRIER);

export function asLang(value: string | null | undefined): Lang {
  return value === "hi" || value === "te" ? value : "en";
}

/** How the patient should read a follow-up's timing: booked or confirmed first, then lateness, then days to go. */
export function dueText(lang: Lang, item: { status: string; days_overdue: number; due_date: string }, today: string): string {
  if (item.status === "BOOKED" || item.status === "COMPLETED") return tItemStatus(lang, item.status);
  if (item.days_overdue === 1) return t(lang, "overdueByOne");
  if (item.days_overdue > 1) return t(lang, "overdueBy", { n: item.days_overdue });
  if (item.status === "CONFIRMED_BY_PATIENT") return tItemStatus(lang, item.status);
  const days = Math.round((Date.parse(`${item.due_date}T00:00:00Z`) - Date.parse(`${today}T00:00:00Z`)) / 86_400_000);
  if (days <= 0) return t(lang, "dueToday");
  if (days === 1) return t(lang, "dueTomorrow");
  return t(lang, "dueInDays", { n: days });
}
