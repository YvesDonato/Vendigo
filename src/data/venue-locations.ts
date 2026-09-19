export type VenueLocation = {
  id: string;
  name: string;
  aliases: string[];
  floor: number;
};

const location = (
  id: string,
  name: string,
  floor: number,
  aliases: string[] = [],
): VenueLocation => ({ id, name, aliases, floor });

export const venueLocations: Record<number, VenueLocation[]> = {
  1: [
    location("f1-sleeping-bag-room-1302", "Sleeping Bag Room 1302", 1, ["sleeping bag room", "1302"]),
    location("f1-activities-room-1327-1331", "Activities Room 1327 / 1331", 1, ["activities room", "1327", "1331"]),
    location("f1-hardware-tool-inventory-1401", "Hardware/Tool Inventory 1401", 1, ["hardware inventory", "tool inventory", "1401"]),
    location("f1-qnx-makerspace-1427", "QNX Makerspace 1427", 1, ["qnx makerspace", "makerspace", "1427"]),
    location("f1-tool-shop-1437", "Tool Shop 1437", 1, ["tool shop", "1437"]),
    location("f1-badge-help", "Badge Help", 1, ["badge help"]),
    location("f1-mentorship-cafe", "Mentorship Cafe", 1, ["mentorship cafe", "mentor cafe"]),
    location("f1-registration", "Registration", 1),
    location("f1-help-desk", "Help Desk", 1, ["help desk"]),
    location("f1-goose-games", "Goose Games", 1, ["goose games"]),
    location("f1-design-bay", "Design Bay", 1, ["design bay"]),
    location("f1-hacking-space", "Hacking Space", 1, ["floor 1 hacking space"]),
    location("f1-hacky-hour", "Hacky Hour", 1, ["hacky hour"]),
    location("f1-pse-main-entrance", "PSE Main Entrance", 1, ["main entrance", "pse entrance", "entrance"]),
    location("f1-elevator", "Elevator", 1, ["floor 1 elevator"]),
    location("f1-water-fountain", "Water Fountain", 1, ["floor 1 water fountain"]),
    location("f1-shower", "Shower", 1),
    location("f1-snack-table", "Snack Table", 1, ["floor 1 snack table"]),
  ],
  2: [
    location("f2-sponsor-event-room-a-2324", "Sponsor Event Room A 2324", 2, ["sponsor event room a", "2324"]),
    location("f2-sponsor-event-room-b-2328", "Sponsor Event Room B 2328", 2, ["sponsor event room b", "2328"]),
    location("f2-sponsor-event-room-c-2317", "Sponsor Event Room C 2317", 2, ["sponsor event room c", "2317"]),
    location("f2-hacking-space-2409", "Hacking Space 2409", 2, ["2409", "floor 2 hacking space"]),
    location("f2-sponsor-bay", "Sponsor Bay", 2, ["sponsor bay", "sponsors"]),
    location("f2-project-expo", "Project Expo", 2, ["project expo", "expo"]),
    location("f2-organizer-hq-2001", "Organizer HQ 2001", 2, ["organizer hq", "organizer headquarters", "2001"]),
    location("f2-volunteer-hq-2004", "Volunteer HQ 2004", 2, ["volunteer hq", "volunteer headquarters", "2004"]),
    location("f2-mlh", "MLH", 2),
    ..."ABCDEFGHIJKL".split("").map((letter) =>
      location(`f2-judging-room-${letter.toLowerCase()}`, `Judging Room ${letter}`, 2, [`judging ${letter.toLowerCase()}`]),
    ),
    location("f2-elevator", "Elevator", 2, ["floor 2 elevator"]),
    location("f2-water-fountain", "Water Fountain", 2, ["floor 2 water fountain"]),
    location("f2-snack-table", "Snack Table", 2, ["floor 2 snack table"]),
    location("f2-crt-table", "CRT Table", 2, ["crt table"]),
    location("f2-e5-exit", "E5 Exit", 2, ["e5 exit"]),
    location("f2-e5-pse-connection", "E5 to PSE Connection", 2, ["e5 pse connection", "pse connection"]),
  ],
  3: [
    location("f3-workshop-3a-3343", "Workshop Room 3A / Wildflower Hall 3343", 3, ["workshop 3a", "wildflower hall", "3343"]),
    location("f3-workshop-3b-3353", "Workshop Room 3B / The Fern Grove 3353", 3, ["workshop 3b", "fern grove", "3353"]),
    location("f3-hacking-space-3051", "Hacking Space 3051", 3, ["3051"]),
    location("f3-hacking-space-3101-3102", "Hacking Space 3101 / 3102", 3, ["3101", "3102"]),
    location("f3-hacking-space", "Hacking Space", 3, ["floor 3 hacking space"]),
    ..."MNOPQR".split("").map((letter) =>
      location(`f3-judging-room-${letter.toLowerCase()}`, `Judging Room ${letter}`, 3, [`judging ${letter.toLowerCase()}`]),
    ),
    location("f3-elevator", "Elevator", 3, ["floor 3 elevator"]),
    location("f3-water-bottle-filling", "Water Bottle Filling Station", 3, ["water bottle station", "filling station"]),
    location("f3-e5-pse-connection", "E5 to PSE Connection", 3, ["floor 3 pse connection"]),
    location("f3-bridge-e6-sleeping", "Bridge to E6 Sleeping Areas", 3, ["e6 sleeping bridge", "bridge to e6"]),
    location("f3-e5-bridge", "E5 Bridge", 3, ["e5 bridge"]),
  ],
  6: [
    location("f6-hacking-space", "Hacking Space", 6, ["floor 6 hacking space"]),
    location("f6-sleeping-room-6008", "Sleeping Room 6008", 6, ["6008"]),
    location("f6-sleeping-room-6006", "Sleeping Room 6006", 6, ["6006"]),
    location("f6-sleeping-room-6004", "Sleeping Room 6004", 6, ["6004"]),
    location("f6-sleeping-space", "Sleeping Space", 6, ["floor 6 sleeping space"]),
    location("f6-wl-mentor-lounge", "WL/Mentor Lounge 6114 / 6116 / 6117 / 6123 / 6127", 6, ["mentor lounge", "wl lounge", "6114", "6116", "6117", "6123", "6127"]),
    location("f6-elevator", "Elevator", 6, ["floor 6 elevator"]),
    location("f6-water-fountain", "Water Fountain", 6, ["floor 6 water fountain"]),
    location("f6-compost", "Compost", 6, ["compost bin"]),
    location("f6-e5-pse-connection", "E5 to PSE Connection", 6, ["floor 6 pse connection"]),
  ],
  7: [
    location("f7-judging-hq", "Judging HQ 7363 / 7303", 7, ["judging hq", "judging headquarters", "7363", "7303"]),
    location("f7-elevator", "Elevator", 7, ["floor 7 elevator"]),
    location("f7-water-fountain", "Water Fountain", 7, ["floor 7 water fountain"]),
    location("f7-multi-faith-quiet-room", "Multi Faith / Quiet Room", 7, ["multi faith room", "quiet room"]),
  ],
};

export const allVenueLocations = Object.values(venueLocations).flat();
