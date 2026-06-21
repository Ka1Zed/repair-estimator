import { useState } from "react";
import RoomPointsTable from "../components/RoomPointsTable";
import RoomPolygonEditor from "../components/RoomPolygonEditor";
import RoomsList from "../components/RoomsList";
import { useProjectStore } from "../store/projectStore";
import OpeningsForm from "../components/OpeningsForm";
import { RoomTypeSelector } from "../components/RoomTypeSelector";

export default function ProjectCreatePage() {
  const [projectName, setProjectName] = useState("");

  const activeRoomIndex = useProjectStore((state) => state.activeRoomIndex);
  const activeRoom = useProjectStore((state) => state.rooms[activeRoomIndex]);
  const rooms = useProjectStore((state) => state.rooms);
  const setHeight = useProjectStore((state) => state.setHeight);

  const handleNext = () => {
    if (!projectName) {
      alert("Пожалуйста, введите название проекта!");
      return;
    }

    const allRoomsValid = rooms.every(
      (r) => r.name.trim() !== "" && r.height !== "" && Number(r.height) > 0,
    );

    if (!allRoomsValid) {
      alert(
        "Ошибка! Убедитесь, что у всех комнат задано имя и корректная высота потолка.",
      );
      return;
    }

    alert(
      `Супер! Данные сохранены.\nПроект: ${projectName}\nВсего комнат: ${rooms.length}`,
    );
  };

  return (
    <div
      style={{
        display: "flex",
        gap: "30px",
        alignItems: "flex-start",
        width: "100%",
        maxWidth: "900px",
        padding: "20px",
        boxSizing: "border-box",
      }}
    >
      <RoomsList />

      <div style={{ flexGrow: 1, color: "#fff" }}>
        <h2 style={{ marginTop: 0 }}>Создание проекта</h2>

        <div style={{ marginBottom: "15px" }}>
          <label>Название проекта:</label>
          <input
            type="text"
            placeholder="Например: Ремонт квартиры"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            style={{
              width: "100%",
              padding: "6px",
              marginTop: "5px",
              background: "#333",
              color: "#fff",
              border: "1px solid #555",
              borderRadius: "4px",
            }}
          />
        </div>

        <div style={{ marginBottom: "15px" }}>
          <label>Высота потолка помещения (м):</label>
          <input
            type="number"
            step="0.1"
            placeholder="2.7"
            value={activeRoom.height}
            onChange={(e) => setHeight(e.target.value)}
            style={{
              width: "100%",
              padding: "6px",
              marginTop: "5px",
              background: "#333",
              color: "#fff",
              border: "1px solid #555",
              borderRadius: "4px",
            }}
          />
        </div>

        {/* Наш новый селектор типов комнат */}
        <RoomTypeSelector />

        <div style={{ marginTop: "20px" }}>
          <RoomPolygonEditor />
        </div>

        <div style={{ marginTop: "20px" }}>
          <RoomPointsTable />
        </div>

        <div style={{ marginTop: "20px" }}>
          <OpeningsForm />
        </div>

        <button
          onClick={handleNext}
          style={{
            padding: "10px 20px",
            cursor: "pointer",
            marginTop: "25px",
            background: "#5cba5c",
            color: "#fff",
            border: "none",
            borderRadius: "4px",
            fontWeight: "bold",
          }}
        >
          Перейти к рисованию
        </button>
      </div>
    </div>
  );
}
